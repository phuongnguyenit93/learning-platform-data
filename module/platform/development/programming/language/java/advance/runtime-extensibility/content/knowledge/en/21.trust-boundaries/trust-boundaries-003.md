# Why ClassLoaders and JPMS Do Not Create a Malware Isolation Environment

## 1. Conclusion and Trust Model

In Java, **`ClassLoader` and the Java Platform Module System (JPMS) primarily manage how classes/modules are loaded, identified, linked, and accessed**, rather than **creating a safe sandbox for untrusted code by themselves**. A plugin running in the same JVM process as the host can still execute Java code allowed at the process level. Without an independent privilege-enforcement mechanism, placing a plugin in its own class loader or its own `ModuleLayer` **does not automatically forbid** it from using OS resources that the Java process is allowed to use.

Two kinds of boundaries must be clearly distinguished:

- **Structural boundaries:** which classes are defined by which loader; which packages are exported/opened by a module; which modules can read other modules; which SPI providers are discovered in a layer. This is the focus of class loaders and JPMS.
- **Trust/security boundaries:** which code is allowed to read files, access the network, use sensitive data, consume CPU/RAM, spawn threads, affect process state, or perform OS operations. Enforcing these permissions must be designed separately.

A common mistaken mental model:

```text
Host JVM
  +-- Loader A / ModuleLayer A --> untrusted plugin
  +-- Loader B / ModuleLayer B --> another plugin

"Dedicated module declarations and classloaders mean plugin A
cannot affect host/plugin B"  <-- WRONG CONCLUSION
```

A more accurate model:

```text
SAME JVM / SAME OS PROCESS
  |
  +-- Host classes / modules
  +-- Loader A -> plugin A
  +-- Layer B  -> plugin B
  |
  +-- Shared Java runtime, heap, and much JVM state
  +-- Usually same OS identity/privileges of the process
  +-- Java SE APIs available per runtime configuration
  +-- Process-level resources and limits

Classloader / ModuleLayer = type organization and module access;
not a barrier for file, network, CPU, or memory permissions.
```

This does not mean class loaders/JPMS are "useless": they are vital for **correctness, encapsulation, modular development, reducing library conflicts, and managing trusted plugins**. However, those benefits must not be interpreted as a guarantee of a sandbox against malicious code.

## 2. What Does a `ClassLoader` Actually Isolate?

### 2.1. Class Identity and Visibility

The JVM distinguishes a class by its **binary name and defining loader**. Two different loaders can define two distinct `com.example.Widget` types, making them incompatible for casting even though their names are identical.

A dedicated loader typically enables:

- Loading a set of JARs used only by the plugin; choosing library versions different from the host's.
- Controlling **class/resource lookup** and parent-child delegation.
- Scoping class metadata and supporting plugin lifecycles; once all relevant references are released, the class loader and its classes can become eligible for GC.
- Sharing only a common API/SPI with the host, rather than letting plugins mix implementation classes.

Example with `URLClassLoader`:

```java
// Illustrative snippet; requires importing java.net.* and java.nio.file.*.
URL jarUrl = Path.of("plugins", "example.jar").toUri().toURL();

try (URLClassLoader pluginLoader = new URLClassLoader(
        new URL[] {jarUrl}, Host.class.getClassLoader())) {
    Class<?> pluginClass =
            Class.forName("demo.plugin.PluginImpl", false, pluginLoader);
    System.out.println(pluginClass.getClassLoader() == pluginLoader);
}
```

This illustrative snippet assumes `Host` and a JAR containing `demo.plugin.PluginImpl` exist; it is **not a standalone program**. The `false` argument to `Class.forName` requests not initializing the class immediately during the call. Having a `Class<?>` loaded through `pluginLoader` only proves a loading/definition boundary; it does **not** prove OS permissions are restricted.

### 2.2. Parent-First and Child-First Are Not Security Mechanisms

Loaders typically use **parent-first delegation**: asking the parent first before searching their own path. Some plugin systems use child-first for implementation libraries to isolate versions. Both are **bytecode lookup policies**, not policies to allow or block business operations or I/O.

Even if a plugin cannot directly reference an internal host package, it can still use **Java SE APIs** permitted by the runtime and host objects already shared with it. For instance, `java.lang.System` belongs to the Java platform; it is not automatically replaced with an "unprivileged" copy for a plugin loader simply because the plugin was loaded from a separate JAR.

More importantly, an untrusted plugin in the same JVM can affect shared state or shared resources it can reach. **Namespace separation does not mean process or privilege separation.**

### 2.3. Bytecode Verification Does Not Verify Safe Intent

The JVM has bytecode verification to enforce format constraints and type safety at the VM level. Valid bytecode can still contain **undesirable logic**: running continuously, consuming excessive memory, writing to data the process is permitted to write, spawning threads, or calling APIs the host did not intend to govern.

Therefore, **"the JAR loads and bytecode passes the verifier" is not a trust certificate**. The verifier helps protect VM invariants within the deployment model; it does not evaluate business impact or replace access-permission checks.

## 3. JPMS Protects Encapsulation, Not a Replacement for a Sandbox

JPMS allows describing dependencies and accessibility between **named modules**. A `module-info.java` might contain:

```java
module demo.plugin {
    requires demo.api;
    exports demo.plugin.spi;
    opens demo.plugin.model to demo.framework;
    provides demo.api.Service with demo.plugin.impl.ServiceImpl;
}
```

This is an **illustrative module descriptor file**; the corresponding modules/packages/classes must exist for it to compile. Meaning of the directives:

| Directive / mechanism | Actual purpose | What must not be inferred |
|---|---|---|
| `requires` | Module declares dependencies and readability relationships | Does not mean "granting permission to access filesystem/network" |
| `exports` | Allows other modules to access public types in the package per Java rules | Does not mean unexported packages create a sandbox |
| `opens` | Allows deep reflection on a package, optionally qualified to specific modules | Not a mechanism to grant or revoke OS privileges |
| `uses` / `provides` | Declares SPI service consumption and provision | Providers are not automatically verified as trustworthy |
| `ModuleLayer` | Groups resolved modules into a layer with ancestor relationships | Does not create a new JVM, separate process, or separate heap |
| `ModuleFinder` / `Configuration` | Locates and resolves modules and their dependencies | Does not verify safe behavior of bytecode |

**A strong boundary still has value:** JPMS enforces access control at the module level, including package export rules and reflection opening. One must not deny that `exports`, `opens`, and strong encapsulation have real enforcement effects. What must be understood is that they govern **access to packages/classes through the module system**, rather than imposing a least-privilege policy on every operation plugin code might ask the JVM to perform.

For example, a named module can use public APIs in `java.base` (an implicit dependency of named modules). Not having `requires demo.host` does not remove access to permitted platform APIs and does not automatically forbid operations on process resources.

### 3.1. `ModuleLayer` Is Not a "Process Container"

`ModuleLayer.boot()` is the initial layer of named modules resolved at JVM startup. A host can create additional dynamic layers to load plugins. A layer may use its own class loader, yet it **remains inside the same JVM**, with shared threads, process privileges, CPU/RAM resources, and much shared runtime state.

Example:

```java
ModuleLayer pluginLayer = ModuleLayer.boot()
        .defineModulesWithOneLoader(
                pluginConfig, ClassLoader.getSystemClassLoader());
```

This is an illustrative snippet assuming `pluginConfig` was already created with a valid `Configuration.resolve`. `defineModulesWithOneLoader` does not grant a kernel namespace, a new user identity, or an isolated RAM quota. It establishes how named modules are defined into a layer using a new loader according to the JPMS API.

### 3.2. Module Readability Is Not Equivalent to Execution Privilege

Learners sometimes reason: "The plugin does not `requires` the host's internal module, so it cannot affect the host." There are two flaws:

1. Not being able to read an internal module may **restrict direct use of that module's Java API**, but it places no constraint on all platform APIs or OS resources.
2. A plugin can interact with the host **through legitimately shared interfaces/objects**. If the host accidentally passes an overly privileged object (such as a service performing admin actions), a well-encapsulated module descriptor does not prevent abuse of that interface.

JPMS supports designing APIs with clear boundaries. It **does not evaluate the intent or trustworthiness of the caller**.

### 3.3. Named, Automatic, and Unnamed Modules Are Not Sandbox Levels

A JAR with `module-info.class` that is resolved can be an explicit named module. A JAR without a descriptor resolved on the module path can be an automatic named module. A JAR on the classpath belongs to the corresponding class loader's unnamed module.

These three packaging/management forms have different access rules, yet they **do not** map to "named module = safe; unnamed module = dangerous". Trustworthiness is a property of **code origin, granted privileges, review, and runtime boundaries**, not merely packaging form.

## 4. What Remains Shared Within the Same JVM

Even when `ClassLoader` and `ModuleLayer` differ, components still live inside **the same Java process**. Exact sharing depends on how loaders are constructed, APIs, and host design, yet critical risks remain:

| Resource / state | Why a separate module/loader is not enough? |
|---|---|
| **Process OS identity and privileges** | The plugin runs with the OS privileges already granted to the JVM process; a loader creates no separate user ID |
| **Heap / garbage collector** | The same JVM shares memory resources; allocation pressure in one plugin can impact the whole process |
| **CPU, threads, and scheduler** | Code running in the process can spawn resource-hungry work; `ModuleLayer` imposes no CPU quota |
| **`System.getProperties()`** and other system state | JVM-wide APIs are shared according to accessibility; a loader does not clone `System` per plugin |
| **`System.out`/`System.err`** | Shared streams and global state are not automatically isolated per layer |
| **File/network APIs** | Capabilities are governed by actual OS/runtime rules, not the plugin's `exports` |
| **Host objects passed into SPI** | If a reference to a mutable/privileged service is passed, the plugin uses the exposed methods |
| **Host JVM lifetime** | A severely buggy or resource-hogging plugin can destabilize the entire application |

For example, a module may be denied access to `com.host.internal.SecretManager` because the package is unexported, yet that **does not prove** it cannot call platform APIs or interact with any valid shared service. Encapsulation protects the API surface; it does not isolate the execution entity.

### 4.1. You Don't Need to "Break" JPMS to See the Limits

This security boundary does not depend on bypassing access controls. A plugin can use APIs that are **completely public and compliant with Java rules** and still produce unintended effects. Therefore, never set "hide all host classes from the plugin" as the goal and consider the threat model complete.

The safe verification in section 5 merely reads a **harmless simulated system property** to demonstrate that both a separately loaded class and a module in a dynamic layer observe **shared JVM state**. No sensitive files, network calls, or harmful operations are used.

## 5. Complete Java 17+ Example: Two Loading Mechanisms, One JVM State

### 5.1. Verification Goal

The host sets a simulated configuration value:

```text
demo.host.mode = ACTIVE
```

Then the host:

1. Loads a plugin class from a JAR outside the application classpath using a dedicated `URLClassLoader`.
2. Defines a named plugin module in a dynamic `ModuleLayer`.
3. Invokes a **public method** on both via legitimate reflection.
4. Observes that both read the system property set by the host, despite differing class loaders and module organization.

This illustrates **shared JVM state**. It does **not** mean every private host object is readable or that all host privileges bypass every other protection mechanism.

### 5.2. File Structure

```text
trust-boundary-demo/
├── classpath-plugin/
│   └── demo/loader/LoaderProbe.java
├── named-plugin/
│   ├── module-info.java
│   └── demo/moduleplugin/ModuleProbe.java
└── host/
    └── Host.java
```

The build produces a plugin JAR at `plugins/loader-plugin.jar`, an exploded named module in `mods/demo.moduleplugin`, and host classes in `out/host`. Only JDK 17+ is required.

### 5.3. Plugin Loaded via `URLClassLoader`

**`classpath-plugin/demo/loader/LoaderProbe.java`**

```java
package demo.loader;

public final class LoaderProbe {
    private LoaderProbe() {
    }

    public static String readMode() {
        return System.getProperty("demo.host.mode");
    }
}
```

The method only reads a property set by the host and touches no external resources. It has no dependency on `Host`.

### 5.4. Named Module Plugin

**`named-plugin/module-info.java`**

```java
module demo.moduleplugin {
    exports demo.moduleplugin;
}
```

**`named-plugin/demo/moduleplugin/ModuleProbe.java`**

```java
package demo.moduleplugin;

public final class ModuleProbe {
    private ModuleProbe() {
    }

    public static String readMode() {
        return System.getProperty("demo.host.mode");
    }
}
```

This module only needs `java.base` (read implicitly) and exports the package containing the public API so the host can call `readMode()` via reflection following module rules. It does **not** require the host to open entire packages or use flags to bypass encapsulation.

### 5.5. Host Creating the ClassLoader and `ModuleLayer`

**`host/Host.java`**

```java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.Set;

public final class Host {
    public static void main(String[] args) throws Exception {
        System.setProperty("demo.host.mode", "ACTIVE");
        System.out.println("host=" + System.getProperty("demo.host.mode"));

        Path jar = Path.of("plugins", "loader-plugin.jar").toAbsolutePath();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {jar.toUri().toURL()},
                Host.class.getClassLoader())) {
            Class<?> type = Class.forName(
                    "demo.loader.LoaderProbe", true, pluginLoader);
            Object value = type.getMethod("readMode").invoke(null);

            System.out.println("loader=" + value);
            System.out.println("loader.separate="
                    + (type.getClassLoader() != Host.class.getClassLoader()));
        }

        ModuleFinder finder = ModuleFinder.of(Path.of("mods"));
        Configuration config =
                ModuleLayer.boot().configuration().resolve(
                        finder, ModuleFinder.of(),
                        Set.of("demo.moduleplugin"));

        ModuleLayer layer =
                ModuleLayer.boot().defineModulesWithOneLoader(
                        config, ClassLoader.getSystemClassLoader());

        Class<?> type = Class.forName(
                "demo.moduleplugin.ModuleProbe",
                true, layer.findLoader("demo.moduleplugin"));

        Object value = type.getMethod("readMode").invoke(null);
        System.out.println("module=" + value);
        System.out.println("module.named=" + type.getModule().isNamed());
    }
}
```

**Key explanations:**

- A new `URLClassLoader` is created to see `loader-plugin.jar`; the host's application classpath does not contain that JAR.
- `LoaderProbe` is a public class defined by `pluginLoader`. `loader.separate=true` shows the loader that loaded the plugin **differs** from the loader that loaded the host.
- `ModuleFinder.of(Path.of("mods"))` discovers the exploded module `demo.moduleplugin`, and `Configuration.resolve` resolves the module against the boot configuration.
- `defineModulesWithOneLoader` creates a new layer using a loader created for that layer's modules with the system loader as parent.
- `ModuleProbe` belongs to a **named module**, confirmed via `getModule().isNamed()`.
- Both plugins call `System.getProperty(...)` from public Java APIs. Reading `ACTIVE` **is not a privilege bypass**: it simply proves that different classes/modules still share JVM-level state.
- The security lesson lies in having **separated loading and module organization without separating process state**.

### 5.6. Compiling and Running on Windows PowerShell

Run the commands below from the `trust-boundary-demo` directory:

```powershell
New-Item -ItemType Directory -Force -Path out\loader,out\host,mods\demo.moduleplugin,plugins | Out-Null

javac -d out\loader classpath-plugin\demo\loader\LoaderProbe.java
jar --create --file plugins\loader-plugin.jar -C out\loader .

javac -d mods\demo.moduleplugin named-plugin\module-info.java named-plugin\demo\moduleplugin\ModuleProbe.java
javac -d out\host host\Host.java

java -cp out\host Host
```

**Expected stdout with the exact structure and no external providers/state interfering:**

```text
host=ACTIVE
loader=ACTIVE
loader.separate=true
module=ACTIVE
module.named=true
```

Do not add the plugin JAR to `-cp`. The module also does not need to appear in the boot layer because the host uses `ModuleFinder` and creates a new layer at runtime. On macOS/Linux, use the equivalent shell directory-creation commands and `/` for paths.

### 5.7. Valid and Invalid Conclusions from the Experiment

**Valid:** placing one class in a separate `URLClassLoader` and one class in a named module inside a separate `ModuleLayer` **does not create separate copies of `java.lang.System` or all JVM state**.

**Invalid:** "Because it can read the property, the plugin has permission to read every private object in the host." Package access rules, module exports, reflection, and object capabilities still apply. The experiment **does not** test access to arbitrary classes, nor does it prove OS policies or other isolation mechanisms fail to work.

**Invalid:** "Simply hiding host packages ensures a plugin cannot affect system resources." Public APIs allowed by the platform and objects intentionally granted by the host still form an impact surface that must be modeled.

**Invalid:** "System properties are visible only because the class loaders have a parent-child relationship." Both classes use the `java.base` platform API. This is an example of **shared state within one JVM**; parent delegation is only a class lookup/definition mechanism, not a division of process memory into security zones.

## 6. When Are ClassLoaders and JPMS Truly Useful?

Do not confuse "not a sandbox" with "has no value". Trusted module/plugin systems still benefit from:

- **Clear class identity:** allows multiple versions of implementation libraries to coexist under control.
- **API boundaries:** host and plugins use only designed interfaces, avoiding accidental access to implementation packages.
- **Module readability and strong encapsulation:** controls Java-level access and certain forms of reflection according to JPMS rules.
- **Declared SPI services:** `uses`/`provides` and `ServiceLoader` discover implementations without hard-coding every class.
- **Layer separation:** new modules can be loaded without placing all of them into the boot layer.
- **Lifecycle and maintenance:** if the host properly manages all callbacks, threads, caches, and resources, old class loaders/layers can become unreferenced and collected.

These points reduce **integration and dependency errors**, but they do not enforce CPU quotas, assign new OS identities, or apply per-plugin file/network read/write controls. If the problem involves untrusted plugins, another **security-enforcing boundary** must be added.

## 7. Does `SecurityManager` Solve the Problem?

In older JDKs, Java had `SecurityManager` and a policy/protection-domain permission model. However, you should not design a new plugin system expecting that simply enabling `SecurityManager` yields a reliable sandbox:

- `SecurityManager` was **deprecated for removal since Java 17** (JEP 411) and subsequently permanently disabled in JDK 24 (JEP 486).
- Class loaders and JPMS **do not automatically replace** a permission checker for system operations.
- Designs intended to run on modern JDKs should use supported isolation mechanisms enforced outside the plugin process or an appropriate capability/host API model, rather than relying on a legacy mechanism that has been removed.

Do not use `System.setSecurityManager` to demonstrate protecting new plugins, as results depend on JDK version and support has changed. In particular, **never** treat a custom class loader as a `SecurityManager` merely because it is programmed to filter certain class names.

## 8. If Plugins Are Untrusted: What Architecture Fits?

### 8.1. Process Separation and Protocol Communication

For plugin code from untrusted sources or external users, an often more suitable approach is running the plugin in a **separate process**:

```text
Host process (critical APIs / credentials)
      |
      | Protocol with schema, validation, and timeouts
      | (IPC / stdin-stdout / local socket / RPC)
      v
Plugin worker process
      |
      +-- Dedicated OS identity/privileges
      +-- Mount or grant only necessary filesystem paths
      +-- Restrict network egress/ingress
      +-- Limit CPU, RAM, process count, execution time
      +-- Logging, monitoring, quotas, and restart policy
```

A process boundary gives the host a chance to **enforce** privileges via the OS or container sandbox. Protection effectiveness depends on actual configuration: merely spawning a new process while sharing the same OS user, the same filesystem, and no quotas still yields limited isolation.

The host must treat all inputs from the worker as **untrusted**: parse data against a schema, check sizes, authenticate identity/source, enforce timeouts, prevent loops, and avoid exposing overly broad capabilities over the protocol. If the host offers the plugin an "arbitrary admin command", process separation cannot rescue a poor permission design.

### 8.2. Limiting Privileges via Least Privilege

Layers of control that can work together:

| Layer | Measure | Purpose |
|---|---|---|
| **OS/container** | Dedicated user/service account, ACLs, filesystem permissions, read-only mounts, network policy | Enforce which resources the plugin is allowed to use |
| **Resources** | CPU/memory/PID limits, timeouts, monitoring/killing policy-violating processes | Limit impact on the host and other plugins |
| **Communication** | IPC/RPC with schema, max sizes, authentication/authorization | Restrict work the host performs on the plugin's behalf |
| **API** | Narrow capability objects, appropriate scope/tenant, input validation | Avoid handing out unbounded admin objects/secrets |
| **Supply chain** | Release signing, hashes, dependency scanning, trusted source allowlists | Reduce the chance of unknown or tampered plugins entering the system |
| **Operations** | Auditing, logging, monitoring, fault isolation, rollback | Detect and recover from incidents |

**Important:** code signing or hash checking verifies **origin/integrity**; it does not make signed code inherently safe. Dependency scanning and reviews are risk-mitigation layers and cannot replace runtime permission policies.

### 8.3. Trusted and Untrusted Plugins Need Two Different Paths

**Plugins built by the same organization, reviewed, and deployed under control:** using class loaders/JPMS within the same JVM can fit well for performance, SPI, object reuse, and avoiding IPC overhead. Even then, lifecycle, errors, resource limits, and incident monitoring must be managed.

**Plugins from third parties or user uploads that cannot be trusted:** treat by default as **untrusted code execution**; prefer process separation with strict OS/container configuration. Never load an untrusted plugin into a high-privilege JVM and rely on `ModuleLayer` or a child-first class loader to stop malware.

**"Sandboxed" script code via a Java `ScriptEngine`** is likewise not automatically safe simply because it runs through `javax.script`. Some engines provide options to restrict interop/permissions, but those must be evaluated and tested on the specific engine; if strong isolation is required, use enforcement outside the JVM.

## 9. Common Design Mistakes

| Misconception | Why it is wrong | Alternative |
|---|---|---|
| "One `URLClassLoader` per plugin is secure" | Loaders separate class identity and lookup paths, not OS privileges | Use loaders for dependency isolation; process sandboxes for untrusted code |
| "Unexported implementation modules cannot cause harm" | Encapsulation blocks Java access to packages, not public runtime APIs | Threat-model capabilities and resources the plugin can use |
| "`ModuleLayer` equals a container" | Still one JVM with shared state and resources | Truly constrained processes/containers |
| "Checking `module-info.java` proves a plugin is trustworthy" | Descriptors describe module structure, not code intent | Source verification, review, and runtime enforcement |
| "`provides` SPI makes `ServiceLoader` automatically safe" | SPI only discovers/instantiates providers per contract; constructors/static init can run code | Activate plugins only from trusted sources or inside isolated workers |
| "Bytecode verifier blocks malicious logic" | The verifier checks structural/type validity, not business intent | Defense-in-depth and privilege separation |
| "Blocking reflection is enough" | Other legitimate APIs still carry whatever OS privileges the process has; code needs no reflection to cause impact | Limit capabilities and OS privileges |
| "`URLClassLoader.close()` completely stops a plugin" | Threads, listeners, and caches can retain old classes/loaders | Stop callbacks/executors/resources, then drop references; monitor leaks |
| "A separate process is unconditionally safe" | A process still has OS privileges and IPC protocols can grant excessive power | Combine OS identity, filesystem/network policies, quotas, and host validation |

### 9.1. Trust and "Permitted to Share Data" Are Two Different Things

A host may intentionally share a `PluginContext` object holding configuration for the plugin to use. That is **fine** when the plugin comes from a trusted source and the object exposes only necessary APIs. Risk arises when the host assumes every script/JAR receiving `PluginContext` is trustworthy, or accidentally passes an object holding more administrative privileges than needed.

Within the same process, an object reference can be a powerful capability. Good SPI design should clearly define **callable methods, tenant scope, lifecycle, and data boundaries**, while actively restricting which objects can reach the plugin.

### 9.2. Failures Still Propagate Even When a Plugin Does Not "Attack"

Even a benign plugin can accidentally keep threads running forever, register callbacks and forget to unregister them, consume too much heap, trigger deadlocks, or flood logs. Class loaders/`ModuleLayer` do not prevent these bugs from affecting the host. Thus, **isolation is a reliability and operational-safety problem, not solely a malware problem**.

## 10. Checklist When Evaluating Plugin Boundaries

1. **Plugin origin:** Who is allowed to introduce JARs/scripts into the system? Are identity, integrity, and approval workflows verified?
2. **Trust level:** Is this a reviewed internal plugin or arbitrary user-supplied code?
3. **Execution privileges:** Does the plugin run in the same process and OS identity as the host? Is there a real sandbox?
4. **Shared APIs:** Are tokens, connections, admin objects, callbacks, or overly broad services passed to the plugin?
5. **Classloader topology:** Are API/SPI interfaces defined and shared with matching class identity? Are duplicate APIs causing cast errors avoided?
6. **Module graph:** Are `requires`, `exports`, `opens`, `uses`, and `provides` properly configured to minimize API surface?
7. **Resources:** Are limits placed on time, CPU, RAM, thread count, file handles, network, and queues?
8. **Lifecycle:** Are listeners, timers, executors, thread-locals, service registries, and resources cleaned up/closed on unload?
9. **Input/output:** Does IPC have schema/validation, size limits, and timeouts? Is every operation authorized?
10. **Observability:** Are metrics, logs, audits, alerts, permission revocation, and recovery paths ready when a plugin misbehaves?
11. **Testing:** Have dependency conflicts, in-flight callbacks, stubborn plugins that refuse to stop, malformed inputs, and memory pressure been tested?
12. **Security claims:** Does documentation clearly distinguish "module encapsulation" from "runtime privilege sandbox" to prevent misunderstandings?

If the only answer is "the plugin has its own loader" or "the plugin is a named module", that is **insufficient grounds** to conclude untrusted code has been isolated.

## 11. Self-Check Questions

1. **Do different class loaders create separate heaps?** No. Classes have distinct identities, yet remain in one JVM sharing the JVM process's memory.
2. **Does a module that exports no packages block all activity of code inside it?** No. It restricts Java access to packages under module rules, without restricting I/O or CPU usage of code in the module.
3. **Why did the example in section 5 use a system property?** To demonstrate shared state via safe behavior, not to show how to bypass access controls.
4. **Is a plugin in its own `ModuleLayer` a separate process?** No, a layer does not create an OS process.
5. **Should `SecurityManager` be the foundation of a modern Java plugin sandbox?** No. This legacy mechanism has been removed from modern JDK support and is not a substitute for process isolation.
6. **Does JAR signing prevent all dangerous plugin behavior?** No. Signing confirms origin/integrity when the verification chain is properly implemented; code from a trusted source can still contain bugs or unwanted behavior.
7. **Is a separate process automatically safe enough?** Not necessarily. OS privileges, resource limits, and strict IPC design must be configured.
8. **Why should an administrative JDBC connection not be handed to an untrusted plugin?** It is a high-privilege capability; class loaders/JPMS do not downgrade the privileges of an object handed over by the host.

**Exercises:** (a) run the program in section 5 and verify both plugins read `ACTIVE`; (b) remove `exports demo.moduleplugin` and observe the restriction when calling the public method from the unnamed host via reflection—only analyze the access error without using flags to bypass access control; (c) redraw your plugin architecture under two models: "same JVM for trusted plugins" and "privilege-restricted worker process for untrusted plugins", listing exactly what is and is not protected.

## 12. References

- Java SE 17 — `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 — `URLClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 — `ModuleLayer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- Java SE 17 — `ModuleFinder` and `Configuration`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/ModuleFinder.html
- Java Language Specification 17, Chapter 7 — Packages and Modules: https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html
- JEP 411 — Deprecate the Security Manager for Removal: https://openjdk.org/jeps/411
- JEP 486 — Permanently Disable the Security Manager: https://openjdk.org/jeps/486
