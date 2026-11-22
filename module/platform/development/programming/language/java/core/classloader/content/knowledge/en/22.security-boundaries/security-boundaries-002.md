# Distinguishing Namespace Isolation from Execution Permission Isolation

## 1. A Separate ClassLoader Does Not Mean a Security Sandbox

Java can use multiple `ClassLoader` instances to load the same binary class name into different runtime types. This helps plugin systems organize dependencies, avoid version conflicts, or replace implementations without restarting the entire application. However, it **must not be inferred** from this that a plugin has separate file, network, CPU, or heap permissions.

There are two completely different questions:

- **Namespace isolation:** When code requests `com.example.Widget`, which ClassLoader defines that class? Can two plugins have different versions of `com.example.Widget`? Which loader sees which resource/JAR?
- **Execution/permission isolation:** What files is plugin code allowed to read/write, where can it connect, can it call native APIs, modify shared state, create processes, or how much CPU/memory can it consume?

Example diagram:

~~~text
                  Host JVM Process
+-------------------------------------------------+
| Application ClassLoader: host + shared API      |
|                                                 |
| Plugin Loader A: class codec.Parser (version 1) |
| Plugin Loader B: class codec.Parser (version 2) |
|                                                 |
|  => A.Parser != B.Parser (runtime class identity)|
|                                                 |
|  SHARED EXECUTION AUTHORITY:                     |
|  * JVM process / OS user                         |
|  * Process filesystem / network permissions     |
|  * Heap, CPU, threads, file descriptors         |
|  * Shared JDK classes, System properties        |
+-------------------------------------------------+
~~~

**Summary:** A ClassLoader is a tool for **finding/defining classes and managing namespaces**. It **does not by itself create a new OS identity or a separate permission policy for plugin bytecode**.

This article belongs to the *Security Boundaries* group and focuses on distinguishing type isolation from execution permissions. You will work through a Java 17+ hands-on example demonstrating that a separately loaded plugin class can still read a test file that the JVM process has permission to read and can modify a JVM-wide system property. Then you will examine SecurityManager, JPMS, process/container isolation, the threat model, and how to build a practical plugin boundary.

## 2. What Does a ClassLoader Guarantee?

### 2.1. Runtime Class Identity Is Tied to the Defining Loader

For ordinary Java classes, a runtime type is typically identified by:

~~~text
(binaryName, definingClassLoader)
~~~

Two different loader objects `L1` and `L2` can both define the name `plugin.impl.Worker`:

~~~java
Class<?> a = loaderA.loadClass("plugin.impl.Worker");
Class<?> b = loaderB.loadClass("plugin.impl.Worker");

System.out.println(a.getName().equals(b.getName())); // may be true
System.out.println(a == b);                           // may be false
~~~

This is an illustrative snippet, not a standalone program: the two loaders must have appropriate class search paths. If both delegate to **the same parent**, `a == b` may be `true` because the parent returns the same class.

To distinguish **which loader actually defined** the class from the loader that was invoked, use:

~~~java
ClassLoader defining = a.getClassLoader();
~~~

A child loader can be the *initiating loader* of a class defined by its parent under the delegation model. Not every `child.loadClass` call causes the child to call `defineClass` itself.

### 2.2. Needs That ClassLoaders Help Solve

| Need | Appropriate Mechanism | What ClassLoaders Do Not Solve |
|---|---|---|
| Plugin A needs version `codec-v1`, B needs `codec-v2` | Per-plugin loader, separating namespaces | Does not grant two different file/network read permissions |
| Host has no compile-time dependency on the implementation | Parent-shared API + loader for the implementation | Does not prevent the plugin from calling public Java APIs |
| Reloading a plugin | Create a new loader, drop references to the old loader when safe | Does not guarantee stopping running code/threads |
| Finding a provider | `ServiceLoader` with an appropriate loader/layer | Does not by itself block the provider from accessing the OS |
| Keeping two classes with the same binary name | Two different defining loaders | Does not create different OS identities |
| Organizing named modules | JPMS/ModuleLayer + loader mapping | Does not by itself limit CPU/memory/network permissions |
| Avoiding resource conflicts | Partitioning JAR paths and delegation | Does not create isolation against code intentionally trying to harm the host |

A ClassLoader is useful for **packaging, compatibility, and class lifecycle**. These boundaries themselves are not sufficient to defend against a malicious plugin in the same process.

### 2.3. A `ClassCastException` Error Is Not a Sign of a Security Boundary

If the `plugin.api.Service` interface is defined by the host and plugin loaders as two runtime classes:

~~~text
HostLoader     -> plugin.api.Service#H
PluginLoader   -> plugin.api.Service#P
~~~

then an implementation of `Service#P` cannot necessarily be cast to `Service#H`. Such a type identity error reflects **two different definitions**; it does not mean the plugin has been restricted from reading files or using the network.

Cross-boundary API design should have the parent loader define **a single shared interface/DTO**, while the child loader loads implementation/private dependencies. Even when API isolation is done correctly, permission isolation remains an independent issue.

## 3. Where Do Execution Permissions Live?

### 3.1. A JVM Process Has Specific OS Permissions

In an application running under a service account, host and plugin threads execute **within the same process**. Without a separate enforced policy, file/socket/process APIs are subject to that process's permissions.

Examples of capabilities that need to be controlled:

- File: reading, creating, writing, deleting, and traversing paths.
- Network: outbound Internet/intranet connections, listening on ports, DNS.
- Process/native: spawning child processes, JNI/FFM when available and permitted by the runtime.
- CPU/RAM/threads: consuming shared JVM resources.
- Secrets: environment variables, secret files, credentials granted to the process.
- Process-wide configuration: `System.setProperty`, global logging, shared registries.
- Shared objects: callbacks, static singletons from parent-defined classes, caches.

**Permission to read one path does not imply permission to read every path.** The OS, the account, and the specific policy govern each operation. However, **different ClassLoaders by themselves do not make those permissions different**.

### 3.2. Shared Classes Have Shared State

Each distinct runtime class has its **own static fields**, even if two classes share the same binary name but have different defining loaders.

Conversely, shared Java platform classes and shared API classes still have shared state. `java.lang.System` is an easy-to-verify example: JVM system properties are shared between host code and plugins in the same process.

~~~java
System.setProperty("example.flag", "changed");
System.out.println(System.getProperty("example.flag"));
~~~

This illustrative snippet does not create a separate map for each plugin. If independent state is needed, pass a dedicated context or move the plugin into a separate process. Also, do not pass secrets into a shared context and expect the loader to prevent the plugin from reading them.

### 3.3. A Different Namespace Does Not Mean a Different Principal

In security design, a **principal/security identity** is the subject to which an authorization policy applies, such as an OS user, a process sandbox identity, or an authenticated service principal. A **ClassLoader object** is not inherently a principal that the OS uses to check permissions.

~~~text
ClassLoader identity:  "Who defined this class?"
OS identity:           "Which process/user is performing the operation?"
Application authz:     "Which operation is this caller allowed to perform?"
~~~

There must be a **real enforcement boundary** between code and resources. Labeling something `SandboxClassLoader` or choosing a separate URL is not enough for the kernel to block file operations.

## 4. Standalone Java 17+ Example: Two Loaders, One Process

The example is safely scoped: the host creates **a temporary file containing only the string MARKER_OK**, passes the `Path` to the plugin, and deletes the file afterward. Plugin A only reads this file and modifies **a dedicated demo-specific system property**; plugin B reads the property back. No internet access, external tools, or special privileges are required.

### 4.1. Project Structure

~~~text
demo/
├── src/
│   ├── plugin/
│   │   └── example/plugin/Probe.java
│   └── host/
│       └── BoundaryDemo.java
└── build/
    ├── plugin/
    │   └── example/plugin/Probe.class
    └── host/
        └── BoundaryDemo.class
~~~

When running, add only `build/host` to the application classpath. **Do not include `build/plugin` in `-cp`**, because if the parent finds `Probe` first, the two child loaders may receive the same class and the identity comparison will no longer demonstrate the intended point.

### 4.2. File `src/plugin/example/plugin/Probe.java`

~~~java
package example.plugin;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Probe {
    public static String readMarker(Path path) throws IOException {
        return Files.readString(path, StandardCharsets.UTF_8);
    }

    public static String readSharedProperty() {
        return System.getProperty("demo.shared.flag");
    }

    public static void changeSharedProperty() {
        System.setProperty("demo.shared.flag", "PLUGIN_CHANGED");
    }
}
~~~

This is a normal plugin implementation with no custom permissions or sandbox-bypass APIs. `Files` and `System` are public JDK classes that plugin code can use when running in a JVM with appropriate permissions.

### 4.3. File `src/host/BoundaryDemo.java`

~~~java
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BoundaryDemo {
    public static void main(String[] args) throws Exception {
        Path marker = Files.createTempFile("plugin-permission-", ".txt");
        try {
            Files.writeString(marker, "MARKER_OK", StandardCharsets.UTF_8);
            System.setProperty("demo.shared.flag", "HOST_INITIAL");
            URL pluginRoot = Path.of("build/plugin").toUri().toURL();
            ClassLoader parent = BoundaryDemo.class.getClassLoader();

            try (URLClassLoader loaderA =
                         new URLClassLoader(new URL[] {pluginRoot}, parent);
                 URLClassLoader loaderB =
                         new URLClassLoader(new URL[] {pluginRoot}, parent)) {

                Class<?> a = loaderA.loadClass("example.plugin.Probe");
                Class<?> b = loaderB.loadClass("example.plugin.Probe");

                System.out.println("sameBinaryName="
                        + a.getName().equals(b.getName()));
                System.out.println("differentRuntimeClasses=" + (a != b));
                System.out.println("differentDefiningLoaders="
                        + (a.getClassLoader() != b.getClassLoader()));

                Method read = a.getMethod("readMarker", Path.class);
                System.out.println("pluginCanReadHostFile="
                        + "MARKER_OK".equals(read.invoke(null, marker)));

                a.getMethod("changeSharedProperty").invoke(null);
                System.out.println("hostSeesPluginPropertyChange="
                        + "PLUGIN_CHANGED".equals(
                                System.getProperty("demo.shared.flag")));

                Method readSetting = b.getMethod("readSharedProperty");
                System.out.println("otherLoaderSeesSameProperty="
                        + "PLUGIN_CHANGED".equals(
                                readSetting.invoke(null)));
            }
        } finally {
            Files.deleteIfExists(marker);
            System.clearProperty("demo.shared.flag");
        }
    }
}
~~~

Explanation:

- `URLClassLoader loaderA` and `loaderB` are **two different objects**, both pointing to the same directory containing bytecode. Each loader defines `example.plugin.Probe` itself because the parent cannot see that class.
- The host is not compiled against `Probe.java`; reflection invokes the public static methods of the loaded class. This is a technique used for the demo, whereas production code can use a shared SPI/interface.
- `Files.createTempFile` creates the marker file, `writeString` writes the text, and `finally` deletes the file when done.
- `Files.readString` runs **in the same process** as the host. A different ClassLoader does not by itself remove the file-reading permissions that the process has.
- `System.setProperty` modifies JVM-wide state, so both the host and plugin B can observe it.
- `try-with-resources` closes the loader resources. This does not mean unloading every defined class or stopping all threads.

### 4.4. Compilation and Execution

Linux/macOS, run from the `demo` directory:

~~~sh
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin src/plugin/example/plugin/Probe.java
javac --release 17 -d build/host src/host/BoundaryDemo.java
java -cp build/host BoundaryDemo
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/plugin, build/host | Out-Null
javac --release 17 -d build/plugin src/plugin/example/plugin/Probe.java
javac --release 17 -d build/host src/host/BoundaryDemo.java
java -cp build/host BoundaryDemo
~~~

### 4.5. Exact Verified Stdout

~~~text
sameBinaryName=true
differentRuntimeClasses=true
differentDefiningLoaders=true
pluginCanReadHostFile=true
hostSeesPluginPropertyChange=true
otherLoaderSeesSameProperty=true
~~~

The demo was compiled with `javac --release 17` and ran successfully on a JDK in a standard environment without enabling the legacy SecurityManager or a special OS policy blocking reading temporary files. The output does not depend on the temporary file name or loader identifier strings.

### 4.6. Reading the Results

| Output | Evidence |
|---|---|
| `sameBinaryName=true` | The two classes have the same binary name |
| `differentRuntimeClasses=true` | The two class objects have different identities |
| `differentDefiningLoaders=true` | Loaders A/B actually defined their own classes |
| `pluginCanReadHostFile=true` | Plugin A can read the marker file created by the host in the same process |
| `hostSeesPluginPropertyChange=true` | Plugin A modifies the global JVM property, and the host sees the change |
| `otherLoaderSeesSameProperty=true` | Plugin B also sees the new state even though B's implementation class is different |

**Do not over-conclude:** The demo only proves that plugin code can read **the marker file whose path was passed to it and that the process is allowed to access**; it does not prove that it can read every file on the machine—that is governed by the OS policy. It proves that **separating class identity does not by itself separate process permissions**.

### 4.7. Extended Experiments

**Experiment A — Add the plugin to the system classpath:** The parent can define `Probe` instead of the two child loaders, causing `differentRuntimeClasses=false`. OS file permissions do not change by themselves.

**Experiment B — Do not pass the `Path` to the plugin:** The plugin does not have that specific path to call the method in the example. However, this is **data-flow control by contract**, not a security boundary against plugin code that can call other public Java APIs.

**Experiment C — Run the plugin in a separate process:** Give the plugin process an OS user/filesystem view without permission to read the marker. If the policy actually blocks it, the code cannot read it even if it knows the path. It is **OS/process enforcement** that makes the difference.

**Experiment D — Add a static field to `Probe`:** Each runtime class of A/B has its own static field. Meanwhile, `System` is a shared JDK class, so its state is shared. It is necessary to distinguish between **statics per runtime class** and **process/shared-class globals**.

## 5. Why Is SecurityManager Not a Modern Solution for a Plugin Sandbox?

In older JDKs, an enabled `SecurityManager` with an appropriate policy could check certain sensitive operations via `Permission`/`ProtectionDomain`. **A separate ClassLoader does not by itself enable that mechanism**; assigning a `CodeSource` or `ProtectionDomain` also does not cause the operating system to grant an independent set of permissions.

Key milestones to remember:

| Version | Behavior to Note |
| --- | --- |
| **JDK 17** | JEP 411 marks `SecurityManager` as **deprecated for removal**; legacy code still depends on policies and configuration. |
| **JDK 17–23** | The ability to enable/install the manager and warnings vary by JDK release; the specific runtime must be checked. |
| **JDK 24+** | JEP 486 **permanently disabled**: it cannot be enabled via a startup flag or `System.setSecurityManager`. |

`CodeSource` describes origin information when available; it is neither artifact verification nor a sandbox. To separate access to files, the network, secrets, and resources between the host and an untrusted plugin, a **process/OS** boundary that is actually configured and tested is required.

References: [JEP 411](https://openjdk.org/jeps/411), [JEP 486](https://openjdk.org/jeps/486), [Oracle JDK 24](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html). The article **SecurityManager Is a Legacy Mechanism and Requires Checking the JDK Version** analyzes the specific legacy APIs, startup flags, and migration.

## 6. JPMS Strong Encapsulation Is Also Different from a Resource Sandbox

JPMS provides:

- `requires`: module readability.
- `exports`: which packages are accessible to other modules according to Java access rules.
- `opens`: opens a package for deep reflection according to context.
- `ModuleLayer`: maps named modules to loader(s) and handles module resolution.

Example descriptor:

~~~java
module plugin.api {
    exports plugin.api;
}
~~~

Preventing deep reflection into a package is **class/member access isolation**, not a restriction on OS operations. A plugin module can still call `java.nio.file.Files` if Java/module access is valid and the OS permits the file operation.

Similarly, `--add-opens` or `--add-exports` options change the scope of Java module access, not network/file ACLs. `ModuleLayer` does not create a kernel namespace or a per-module CPU quota. The module graph and loader mapping are application-structuring tools, not a container.

## 7. Choosing a Boundary Based on Trust Level

### 7.1. Internal, Reviewed Plugins

When code is developed and reviewed by the same team, running in the same JVM with a separate ClassLoader can be a reasonable choice:

- Easy to call Java interfaces directly, with low IPC overhead.
- Supports multiple versions of libraries.
- Allows a plugin lifecycle and reloading with a new loader.
- Shared API is defined once by the parent loader.
- Allows `ServiceLoader`/module layers for discovery.

However, resource leaks, timeouts, exception propagation, shared state, and version conflicts still need to be handled. **High trust** does not mean the code cannot have bugs or affect the host.

### 7.2. Third-Party or Multi-Tenant Plugins

If the plugin is not in the same trust domain, the execution boundary can be:

~~~text
Trusted host JVM
      |
      | IPC request/response + authz
      v
Isolated plugin runner process
  - dedicated OS identity / limited credentials
  - filesystem mounts / allowlists
  - network egress and ingress rules
  - CPU, memory, PID, FD quotas
  - timeout, restart, supervision
      |
      v
Plugin's own ClassLoader (if namespace isolation is still needed)
~~~

The host does not arbitrarily share the object heap and process privileges with the plugin. A loader inside the runner is still useful for dependencies, but **execution permissions are protected at the process/OS boundary**.

### 7.3. Containers, Sandboxes, and Virtual Machines

Containers can provide useful isolation, but the level of security depends on configuration:

- Do not grant privileged access, and do not unnecessarily mount host secrets/filesystems/the Docker socket.
- Use minimal OS user/capabilities; use rootless mode/user namespaces when appropriate.
- Restrict network egress, seccomp/AppArmor/SELinux, mounts, and read-only paths according to the environment.
- Apply quotas and a restart policy; monitor logs and resource usage.
- Keep the kernel/runtime patched; verify images and dependencies.

Containers usually share the kernel with the host. When the threat model requires stronger isolation, consider a VM/hypervisor, controlled process isolation, or a dedicated execution service. No boundary is secure by name alone.

### 7.4. An API Allowlist Is Good Design but Insufficient Against Adversarial Code

A host might only expose:

~~~java
public interface PluginContext {
    byte[] readApprovedResource(String id) throws Exception;
    void emitOutput(String value);
}
~~~

This is an illustrative contract. For **cooperative code**, limiting methods by capability makes the design clearer. However, if arbitrary plugin bytecode in the same JVM can still access public JDK APIs, it **can bypass the host-proposed API**. To enforce restrictions on untrusted code, the policy must be placed at a boundary that cannot be bypassed (OS/process/IPC).

### 7.5. Decision Table

| Criterion | Single JVM, Separate ClassLoader | Separate Process + OS Policy |
|---|---|---|
| Namespace/version isolation | Can be achieved well | Yes, plus a process boundary |
| Shared Java objects | Direct via shared API | Uses IPC/serialization |
| Blocking access to host secret files | **Cannot do by itself** | Possible if user/mounts/credentials are configured properly |
| Network allowlist per plugin | **Cannot do by itself** | Possible if the policy is enforced |
| CPU/memory quota per plugin | No reliable per-loader quota | Process/container quotas can be applied |
| A plugin crash killing the host | No isolation guarantee | The host can keep its own process running |
| Deployment, debugging, latency | Simpler | More complex, IPC overhead |
| Trusted plugins | Usually sufficient for namespaces | Consider if fault isolation is needed |
| Adversarial/untrusted plugins | **Insufficient** | Requires a stronger execution boundary |

**Separating namespaces is an engineering goal; separating permissions is a security goal.** Choose based on the threat model, not just code structure.

## 8. Risks That ClassLoaders Cannot Eliminate on Their Own

### 8.1. Files and Network

If the JVM runs under an account that has permission to read a secret file, a class defined by a child loader **does not automatically lose that permission**. The plugin can call public file/network APIs, subject to OS permission checks just like other threads in the process.

If tenants need to be separated: provision secrets into separate runners or design a broker with authorization; do not use `ClassLoader == tenantIdentity` in place of a real ACL.

### 8.2. Shared State and Cross-Plugin Interference

A plugin can affect `System` properties, global logs, static shared caches, callbacks/registries, and mutable objects passed in by the host. Creating a separate ClassLoader does not create separate copies of shared JDK classes.

Designing with minimal shared mutable state, using immutable DTOs, and having clear interface boundaries can reduce logic bugs, but for untrusted bytecode, enforcement outside Java object conventions is required.

### 8.3. Denial of Service

A plugin can monopolize CPU, allocate excessive memory, spawn threads, or hold file descriptors. There is no default **per-ClassLoader** CPU/heap/thread quota.

`Future.cancel(true)` or `Thread.interrupt()` is helpful when code cooperates, **not a reliable kill switch** for buggy or adversarial code. `Thread.stop()` is not a safe option for sandboxing. A separate runner process can be terminated/restarted according to system policy.

### 8.4. Class Unloading Is Not Revocation

`URLClassLoader.close()` releases the loader's resources, but does not guarantee that all loaded classes are immediately unloaded; instances, threads, `Thread Context ClassLoader`, caches, and method handles can keep them alive. Closing a loader **does not by itself revoke the OS authority** of running thread/plugin code.

If forced permission revocation is needed, the separate process can be stopped/killed and credentials/network policies revoked; that is completely different from dropping a ClassLoader reference.

### 8.5. Type Safety Does Not Mean Authorization

The JVM bytecode verifier and class-loading rules protect the consistency of the type system. A **type-safe** program can still perform unwanted actions using legitimate APIs with the permissions the process already has.

**"The JVM refuses to define a class with a duplicate name" does not prove that the JVM blocks all file/network actions of plugin code.**

## 9. Process for Designing and Verifying a Plugin Boundary

Start with a **threat model**, then select techniques matching the actual source of risk:

1. **Who controls the bytecode?** Reviewed internal code, an approved partner, or arbitrary users? Check the publisher, artifact, dependencies, and the possibility of tampering before execution.
2. **Which resources must be kept separate?** Secrets, databases, the filesystem, the network, process lifetime, or the permissions of other tenants. Identify who currently has OS access to them.
3. **What is the isolation goal?** If it is only to let each plugin use its own library version, a ClassLoader can be used. If adversarial code behavior must be blocked, a separate process and OS policies are needed.
4. **How does communication cross the boundary?** The host must perform AuthN/AuthZ, validate inputs and outputs, and enforce limits on message size, timeouts, retries, and allowed operations; worker output remains untrusted data.
5. **How do you prove that permissions are blocked?** In the actual deployment environment, attempt to read a mock file outside the allowlist and connect to a forbidden test endpoint; verify that the OS denies them, along with CPU/memory quotas and cleanup after timeouts.

```text
Artifact/source gate → ClassLoader/JPMS (namespace)
                     → Process/OS policy (permissions/quotas)
                     → IPC authorization & validation → Monitoring
```

Each layer addresses a distinct question. A Java API allowlist provided by the host is useful for cooperative plugins, but does not prevent adversarial bytecode in the same JVM from calling public JDK APIs itself. Details on supervisors, pipes, timeouts, process trees, and IPC are covered in the article **Process Isolation When a Stronger Security Boundary Than ClassLoader Is Needed**.

## 10. Common Misconceptions

### "Two plugins have the same class name but different ClassLoaders, so they are isolated"

**Partially true:** They may be two different runtime types, which helps avoid namespace collisions. **False regarding file/network permissions:** Threads can still share the same process authority.

### "JPMS prevents the plugin from reflecting into private fields, so the plugin cannot read secrets"

Insufficient. JPMS restricts Java module access, but if a secret exists in a file, environment variable, or IPC that the process still has permission to read, a separate policy is needed. Also, do not inadvertently put secrets into a shared object graph.

### "The plugin is only given a small PluginContext, so it definitely cannot call File APIs"

Not true for arbitrary bytecode in the same JVM without other enforcement. An interface boundary is good for design, but does not by itself block uncooperative code.

### "JEP 411 only deprecated it; we can still keep SecurityManager enabled indefinitely"

False: **JEP 486 in JDK 24 permanently disabled it**. A design relying on `java.policy` has no sustainable path forward for newer JDKs.

### "A container is an absolute sandbox"

No. Containers require proper configuration of least privilege, mounts, secrets, egress, capabilities, quotas, and kernel updates. For a stronger threat model, consider a VM/hypervisor.

### "Closing the loader stops the plugin"

No. Loaded classes, instances, and threads may still remain alive; the process's OS resources remain unchanged. Lifecycle/shutdown logic is needed, or killing/restarting the process at a separate boundary.

### "What does a JAR signature allow a plugin to do?"

A signature primarily serves to verify artifact integrity/origin; it **is not by itself an I/O-restricting policy**. Having trusted provenance does not mean the code has no bugs or cannot abuse process resources.

### "A separate ClassLoader has an independent JVM heap/GC"

False: there is no separate heap, garbage collector, or CPU scheduler per ClassLoader by default. Resources can be measured/limited per process/container, not automatically per loader.

## 11. Self-Check Questions and Exercises

1. What question does namespace isolation answer? What question does permission isolation answer?
2. Which components is the runtime type identity of an ordinary class tied to?
3. Why can two different ClassLoaders still return the same `Class<?>`?
4. Why is a `ClassCastException` caused by different loaders not proof that a sandbox is working?
5. Does a ClassLoader by itself create a different OS identity or file-permission account?
6. In the demo, why do two different runtime classes both see the same `System` properties?
7. Is a static field in `Probe` defined by loader A shared with B's version of `Probe`?
8. What does `pluginCanReadHostFile=true` prove, and what does it **not** prove?
9. If a plugin truly must not read a secret file, where must the enforcement boundary be placed?
10. How do `ServiceLoader`/`URLClassLoader` help with discovery and dependency problems?
11. Do `ModuleLayer` and `exports`/`opens` by themselves prevent network egress?
12. Which Java version is JEP 411 associated with, and which JDK is JEP 486 associated with?
13. Why do `ProtectionDomain`/`CodeSource` not by themselves guarantee a file/network sandbox on JDK 24+?
14. How is using a `PluginContext` API wrapper useful even though it is insufficient against adversarial bytecode?
15. Why can an uncooperative plugin make timeout/cancellation in the same JVM unreliable?
16. Why does URLClassLoader.close not guarantee stopping threads and revoking OS permissions?
17. When plugins A and B need two library versions, by what criteria do you choose a separate ClassLoader versus a separate process?
18. What conditions must be controlled in a container to avoid leaking host secrets?
19. When moving a plugin behind IPC, what elements does the host need to validate/authorize?
20. Can a signed artifact still run with bugs or cause resource exhaustion?
21. Where are real CPU/memory quotas enforced?
22. Why should permission boundaries be tested on an actual build/deployment rather than only in an IDE?
23. In a multi-tenant system, why is one ClassLoader per tenant not equivalent to one security principal per tenant?
24. Redraw the three-layer diagram: classloader namespace, Java module access, and OS/process permissions.
25. Give one scenario where a separate ClassLoader is **the right solution** and one scenario where it is **insufficient**.

**Completion criteria:** Run and explain all six lines of stdout; prove that type identity can differ while process permissions are still shared; distinguish Java access control from OS authorization; know the status of SecurityManager in Java 17/JDK 24+; propose a way to genuinely separate execution permissions when running untrusted plugins.

## 12. Authoritative References

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, parent delegation, and class namespace.
- [JLS §12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2): consistency/identity of class loading.
- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module-layer mapping, not an OS sandbox.
- [Java SE 17 — ProtectionDomain](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html): protection domain in the historical Java security architecture.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): SecurityManager deprecated for removal since Java 17.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): SecurityManager disabled in JDK 24.
- [Oracle JDK 24 Security Developer's Guide](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): changes to permission APIs and guidance on migrating to containers/OS/VMs.

**Conclusion:** A ClassLoader separates **namespaces and runtime type identity**; JPMS enforces **module readability and Java access control**; whereas **file/network/process permissions and resource quotas** must be enforced by an appropriate OS/process/runtime boundary. Do not call a child ClassLoader a security sandbox unless a policy is enforced outside the class-loading mechanism.
