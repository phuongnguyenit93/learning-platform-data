# Why ClassLoader Does Not Create a Security Sandbox for Java Plugins

> **Java Core → ClassLoader → Plugin Architecture.** `ClassLoader` helps control **where to find bytecode**, **which class belongs to which namespace**, and **the delegation relationship between host and plugin**. It does not create a security boundary equivalent to a process, an operating system user, or a container. A plugin with normal Java bytecode, after being loaded into the same JVM, can generally still invoke platform APIs with the permissions that the **JVM process** holds. This lesson distinguishes class isolation, module encapsulation, historical security metadata, and actual sandboxes; it includes a Java 17+ example that has been run and verified.

## 1. Properly Understanding the Problem and Threat Model

Suppose a host system allows loading a JAR containing a plugin:

```text
Host JVM process
├── Host application classes
├── Plugin API: com.example.api.Plugin
├── Plugin ClassLoader A
│   ├── plugin-a.jar
│   └── some separate dependencies
└── Plugin ClassLoader B
    ├── plugin-b.jar
    └── different dependency versions
```

Such a design can solve reasonable problems:

- Two plugins using two versions of a library with the same name but different defining loaders.
- Not automatically placing plugin A's implementation into plugin B's search path.
- Allowing plugins to communicate with the host through a shared API with the same `Class<?>` identity.
- Managing plugin generations: creating a new loader on update and releasing references to the old loader when possible.
- Keeping the class and resource lookup structure explainable and testable.

**However:** if plugin A is untrusted bytecode, the question shifts in a different direction: "Can the plugin read the host's files, connect to the network, modify global state, or terminate the process?" Merely separating loaders **provides no guarantee of preventing those actions**.

### Three Different Trust Models

| Plugin Model | Goal | Is ClassLoader Sufficient? |
| --- | --- | --- |
| **Trusted** plugins with different dependencies | Separate libraries, avoid `ClassCastException`/collisions, manage lifecycle. | Useful and often suitable, though state must still be managed. |
| **Semi-trusted** plugins cooperating by contract | Limit accidental errors via API/plugin contracts, validation, and timeouts. | Partially useful; does not guarantee protection against code intentionally bypassing the contract. |
| **Untrusted or potentially malicious** plugins | Protect data, files, network, process, and resources from arbitrary executing code. | **No.** Requires a stronger execution boundary such as a separate process with restricted OS permissions. |

**The threat model dictates the solution:** avoiding class conflicts is completely different from defending against a plugin intentionally stealing data, disrupting the service, or bypassing permission controls.

## 2. What Does ClassLoader Actually Isolate?

The JVM identifies an ordinary class/interface by the pair **(binary name, defining loader)**.

```text
Loader A -> com.plugin.Widget (Class A)
Loader B -> com.plugin.Widget (Class B)

Same binary name
Defined by different loaders
=> Class A != Class B
```

Consequences:

- Having the same name `com.plugin.Widget` does not necessarily mean having the same runtime type.
- Two classes belonging to two different loaders can encounter `ClassCastException` when casting, even if the code looks identical.
- Runtime `Package`, package-private access, and package metadata are partitioned by the defining loader.
- A loader only searches for resources/classes within its source scope and delegation policy, and does not automatically read every JAR outside its search path.
- The TCCL (`Thread.currentThread().getContextClassLoader()`) may be used by frameworks to locate providers/resources other than the system loader.

This is **namespace and dependency isolation**. It is an important property for a plugin architecture, but it is **not a policy prohibiting the use of Java APIs**.

### Parent Delegation Is Not a Firewall

The common `ClassLoader.loadClass` lookup path uses parent-first:

```text
pluginLoader.loadClass("java.nio.file.Files")
    |
    v
parent / platform / bootstrap lookup
    |
    '--> java.nio.file.Files is returned from the Java runtime
```

Parent delegation helps unify core platform classes and share APIs; it does not block plugins from using those very APIs. Preventing a plugin from **redefining** `java.lang.String` does not mean preventing the plugin from **calling** `java.lang.String`, `Files`, `Socket`, `ProcessBuilder`, or other JDK methods accessible to it.

Do not simply set `parent = null` and call that a "sandbox". A null parent requests delegation to the bootstrap loader under `ClassLoader` semantics; many platform APIs still exist. Furthermore, class loading constraints and namespaces must be respected regardless of which parent is chosen.

## 3. What Is NOT Prevented by a Class Loader?

Once a class has been accepted by the JVM and begins executing, its bytecode can directly call public APIs permitted by module/access rules and the environment. Some notable examples:

| Plugin Capability | Does ClassLoader Block It on Its Own? | Risk to the Host |
| --- | --- | --- |
| `Files.readString(Path)` | No. | Reads files the process has permission to access, if the path is known or guessed. |
| `Files.writeString(Path, ...)` | No. | Modifies/deletes data that the OS account has permission to access. |
| `System.getProperty`, `System.getenv` | No. | Reads system properties/environment variables available in the process. |
| `Socket`, `HttpClient` | No. | Makes outbound connections if the network policy allows. |
| `ProcessBuilder` | No. | Spawns child processes if allowed by the OS/runtime. |
| `System.exit` | ClassLoader does not guarantee blocking it. | Can terminate the entire JVM containing the host. |
| Creating threads, holding locks, CPU loops, allocating memory | No. | Contention/stalls, memory pressure, denial of service. |
| Calling public host APIs or capturing passed references | No. | Mutates shared state depending on the exposed APIs/objects. |
| Reflection | Not governed by ClassLoader rules; JPMS also controls reflection. | Can access additional members when modules/packages are opened appropriately. |

External conditions still apply: filesystem ACLs, OS user permissions, SELinux/AppArmor, container configuration, network policies, JPMS access, and certain permissions of specialized APIs. However, **these mechanisms are not guarantees created by ClassLoader**.

Do not interpret the table as "every call always succeeds": an operation can fail due to OS permissions, a non-existent path, a blocked network, module encapsulation, or another security policy. The point to remember is that **changing the loader does not itself establish a deny policy for those operations**.

### "Not Providing Dangerous APIs to Plugins" Is Not Enough

A host might expose an interface containing only:

```java
public interface PluginContext {
    String readPublicConfig();
    void emitEvent(String event);
}
```

This is a **Java snippet** illustrating a contract, not a standalone program. For trusted plugins, a contract helps produce a good design. However, if plugin bytecode is allowed to execute **arbitrary Java code in the same JVM**, it can directly call `Files`, `HttpClient`, or other APIs without going through `PluginContext`. A restricted wrapper API **does not create a sandbox** without additional enforcement at the runtime/OS/process level.

## 4. SecureClassLoader Has "Secure" in Its Name, But It Does Not Make Plugins Safe

`java.security.SecureClassLoader` extends `ClassLoader` and provides APIs to associate a `CodeSource`, `ProtectionDomain`, and `PermissionCollection` with a defined class.

```java
protected final Class<?> defineClass(
    String name, byte[] bytes, int offset, int length,
    java.security.CodeSource source);

protected java.security.PermissionCollection getPermissions(
    java.security.CodeSource source);
```

These are **abbreviated API signatures**, not to be copied into a standalone Java file. Subclasses can override `getPermissions` to supply permission metadata for the constructed domain.

Historically:

```text
SecureClassLoader.defineClass(..., CodeSource)
       |
       v
CodeSource(location, certificates)
       |
       v
getPermissions(CodeSource)
       |
       v
ProtectionDomain
       |
       v
Class<?> associated with the domain
       |
       v
Legacy SecurityManager/Policy (when previously enabled)
       |
       '--> the platform could check permissions at protected operations
```

**When the Security Manager is not enabled**, an empty permission set does not protect the filesystem or network on its own. **Starting in JDK 24**, the Security Manager is permanently disabled per JEP 486. Modern `SecureClassLoader` Javadoc also explicitly states that permissions are no longer used to control resource access when the Security Manager is not supported.

`CodeSource` can still be useful for metadata/provenance, but:

- `CodeSource.location` can be a URL **assigned by the loader itself**; it does not prove that the bytes have had their origin verified.
- `CodeSource` does not by itself prove that a JAR is signed or trusted; if signing is used, an appropriate verification process is required.
- `ProtectionDomain.getPermissions()` may hold an empty collection, yet that does not automatically block `Files.readString` on JDK 24+.
- Certificate consistency, class-format verification, package sealing, module access, and `SecurityManager` are distinct concepts; they do not substitute for one another.

## 5. Why Is SecurityManager No Longer a Path for Building New Sandboxes?

Previously, Java had a permission-checking model based on the Security Manager:

- `CodeSource` and the domain linked a class to a code source.
- `java.security.Policy` could define `FilePermission`, `SocketPermission`, `PropertyPermission`, etc.
- When `SecurityManager` was enabled, APIs with built-in permission checks could allow or deny operations.
- `AccessController` participated in the stack-based access control model and `doPrivileged`.

However, this mechanism had high complexity, limited adoption, and never provided an isolation guarantee against every issue (native code, shared resources, side channels, and other risks).

Timeline:

| Java/JDK | Status |
| --- | --- |
| Java 8/11 and earlier releases | The Security Manager could be used in environments where it was enabled and properly configured; by default, applications typically ran without a sandbox. |
| Java 17 | **JEP 411** deprecated the Security Manager **for removal**. |
| Java 17–23 | Legacy capabilities remained present but came with warnings/restrictions depending on the version. |
| **JDK 24+** | **JEP 486** permanently disabled the Security Manager. It cannot be installed/re-enabled via the launcher or `System.setSecurityManager`. |

On JDK 24+, `System.getSecurityManager()` returns `null`; `System.setSecurityManager(...)` throws `UnsupportedOperationException`; legacy-style policy properties provide no enforcement. `AccessController.checkPermission(...)` may also **unconditionally throw `AccessControlException`** for API compatibility, yet that does **not** mean file/network APIs are protected as they used to be.

The key point when migrating legacy plugin frameworks: do not merely replace syntax, but move **security boundary enforcement** to an appropriate system. See the Oracle documentation on disabling the Security Manager and JEP 486 at the end of this lesson.

## 6. Hands-on Java 17+: A Plugin Reads a Test File Even Though the Domain Grants No FilePermission

This experiment is a **safe demonstration that only reads a file created by the host itself in a temporary directory**. The host creates a file containing the text `training-only` and tells the plugin its path via the `demo.resource.path` property so the result is reproducible; the plugin uses `Files.readString` to read that file **without going through the host's plugin API**.

The goal is not to access confidential data or bypass OS controls. The goal is to observe that **a SecureClassLoader returning an empty permission collection does not prevent Java code in the same JVM from reading resources that the process is permitted to read when there is no Security Manager**.

### Project Structure

```text
src/
  plugin/
    demo/
      Worker.java
  app/
    LoaderSandboxDemo.java
plugin-classes/  (created by javac)
app-classes/     (created by javac)
```

**File `src/plugin/demo/Worker.java`:**

```java
package plugin.demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Worker {
    public static String readHostFile() throws IOException {
        String path = System.getProperty("demo.resource.path");
        return Files.readString(Path.of(path)).trim();
    }
}
```

**File `src/app/LoaderSandboxDemo.java`:**

```java
import java.io.FilePermission;
import java.io.IOException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.CodeSource;
import java.security.PermissionCollection;
import java.security.Permissions;
import java.security.SecureClassLoader;
import java.security.cert.Certificate;

public final class LoaderSandboxDemo {
    static final class PluginLoader extends SecureClassLoader {
        private final Path root;
        private final URL origin;

        PluginLoader(Path root) throws IOException {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath();
            this.origin = this.root.toUri().toURL();
        }

        @Override
        protected PermissionCollection getPermissions(CodeSource cs) {
            return new Permissions();
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            try {
                byte[] data = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                CodeSource cs = new CodeSource(
                        origin, (Certificate[]) null);
                return defineClass(name, data, 0, data.length, cs);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path example =
                Files.createTempFile("harmless-demo-", ".txt");
        try {
            Files.writeString(
                    example, "training-only",
                    StandardCharsets.UTF_8);
            System.setProperty(
                    "demo.resource.path", example.toString());

            PluginLoader loader =
                    new PluginLoader(Path.of("plugin-classes"));
            Class<?> worker = Class.forName(
                    "plugin.demo.Worker", true, loader);

            System.out.println("owned by plugin loader: "
                    + (worker.getClassLoader() == loader));
            System.out.println("code source present: "
                    + (worker.getProtectionDomain()
                            .getCodeSource() != null));

            boolean granted = worker.getProtectionDomain()
                    .getPermissions()
                    .implies(new FilePermission(
                            example.toString(), "read"));

            System.out.println(
                    "file permission in domain: " + granted);

            String value = (String) worker
                    .getMethod("readHostFile")
                    .invoke(null);
            System.out.println("plugin file read: " + value);

            System.out.println("same class on reload: "
                    + (Class.forName(
                            "plugin.demo.Worker", false, loader)
                            == worker));
        } finally {
            System.clearProperty("demo.resource.path");
            Files.deleteIfExists(example);
        }
    }
}
```

### Compiling and Running

From the directory containing `src`:

```bash
javac --release 17 -d plugin-classes src/plugin/demo/Worker.java
javac --release 17 -d app-classes src/app/LoaderSandboxDemo.java
java -cp app-classes LoaderSandboxDemo
```

Do not put `plugin-classes` on the application classpath. The host's loader only receives `app-classes`, while the custom loader finds the `plugin.demo.Worker` bytecode from `plugin-classes`. The program uses APIs already available in Java 17+.

**Exact stdout verified on OpenJDK 24 with `javac --release 17`:**

```text
owned by plugin loader: true
code source present: true
file permission in domain: false
plugin file read: training-only
same class on reload: true
```

### Explaining the 5 Lines of Output

1. `owned by plugin loader: true`: it is the `PluginLoader` instance that is the defining loader of `plugin.demo.Worker`; the parent did not define that class.
2. `code source present: true`: the `SecureClassLoader.defineClass` overload attached a `CodeSource`; source information **is not a safety certificate**.
3. `file permission in domain: false`: `getPermissions` returns an empty collection, so `PermissionCollection.implies(FilePermission(path,"read"))` is `false`.
4. **`plugin file read: training-only`:** the plugin still reads the file created by the host via direct `Files.readString` when the JVM does not use a Security Manager to deny access by domain. This is what needed to be demonstrated.
5. `same class on reload: true`: with the same binary name and defining loader, the subsequent load reuses the `Class<?>`; this property belongs to class loading, not authorization.

**Environment note:** On JDK 24+ there is no Security Manager enabled, so the demonstrated result occurs under standard configuration when not blocked by the OS. On JDK 17–23, when **the Security Manager is not enabled**, the same principle applies; if the legacy Security Manager is explicitly enabled with an appropriate policy, the file-reading behavior may differ. This example **does not require** and **does not instruct** enabling the Security Manager.

**Safety scope note:** The host itself supplies the path to a file that it creates and deletes after the test. That illustrates that the loader does not block OS operations that the process is allowed to perform; it does **not** test guessing secret paths, signing JARs, or exploiting OS vulnerabilities. Do not place real secrets into system properties to simulate this test.

## 7. Why Exposing Only Safe Methods in the Host API Still Does Not Create a Sandbox

A host might design:

```java
public interface Plugin {
    void execute(PluginContext ctx);
}

public interface PluginContext {
    String getPublicGreeting();
}
```

These are **two illustrative declarations** that need to be separated into `Plugin.java` and `PluginContext.java` if you want to compile them. If a plugin only voluntarily uses `ctx.getPublicGreeting()`, the API contract helps reduce misuse.

However, arbitrary plugin bytecode can also write:

```java
// Conceptual example inside plugin code:
String runtime = System.getProperty("java.version");
java.nio.file.Path path = java.nio.file.Path.of("config.txt");
// If the OS process has permission, the plugin can use the Files API.
```

There is no mechanism in a default `ClassLoader` that forces a plugin to call `ctx` instead of the JDK library. Not handing a direct reference to a database client to the plugin is also not enough if it still has credentials in the environment/process or permission to read the config file containing the connection string.

**Object capability and trust boundary:** A controlled API contract is useful if the plugin is **trusted** or executes inside an actual sandbox that blocks permissions outside the contract. If a malicious plugin runs in the same process and still invokes JDK APIs, restricting only `PluginContext` is a measure of **architectural discipline**, not an absolute defense.

## 8. JPMS Is Stronger Than Classpath Encapsulation, But It Is Also Not a Sandbox

Since Java 9, named modules have `requires`, `exports`, and `opens`:

```java
module com.example.host {
    exports com.example.plugin.api;
    // Does not export/open the host's own implementation packages.
}
```

JPMS helps control:

- Which module **reads** which module.
- Which package's public API is **exported** to other modules.
- Which packages are **opened** for deep reflective access.
- Certain reflective/bytecode accesses to internals are blocked according to the module graph.

However:

- `module-info.java` is not a "plugins cannot read any files" policy.
- A plugin can still use permitted public APIs of `java.base`, such as `java.nio.file.Files` and `System.getProperty`.
- `--add-opens` and `--add-exports` open additional module boundaries when frameworks need them; overusing them weakens encapsulation, rather than creating file/network isolation.
- An unexported module can reduce one direct access path to internal host classes, but it is **not sufficient** against plugin code running in the same OS process with its existing permissions.
- Reflection and native/JNI/FFM have their own access rules; do not equate "using modules" with "unable to perform dangerous actions".

Use JPMS to build clear module API boundaries. When untrusted code needs to be isolated, add a security boundary at the **process, OS, and infrastructure** layer.

## 9. Class-Loader Lifecycle Does Not Mean Resource Isolation

A new loader can load the same binary name in a different generation, but it does not transfer old object/static state or create a new permission boundary. `URLClassLoader.close()` only closes resources belonging to the loader; it does not stop threads or undo filesystem/network side effects. The TCCL, registries, threads, and static/global state can keep a plugin alive or allow the plugin to affect the shared process. This is another reason to distinguish lifecycle cleanup from **security isolation**.

## 10. Appropriate Workflow for Trusted Plugins

If plugins are controlled/approved by your team, need dynamic loading, and require library compatibility, class loaders remain the right tool. Reference architecture:

```text
Host application
    |
    +--> shared plugin API (host/parent loader)
    |
    +--> PluginLoader A -> plugin-a.jar + dependencies A
    |
    '--> PluginLoader B -> plugin-b.jar + dependencies B
```

Principles:

1. **Shared API** defined by the parent loader. Implementations in a plugin loader can implement this interface and still be cast to the host's API.
2. **Do not package duplicate copies of the API** in each plugin child loader if the child defines its own copy; doing so creates incompatible runtime types.
3. **Make a clear delegation decision**. Parent-first is usually easier to reason about; child-first, if justified by library version reasons, must avoid shadowing JDK/host APIs and handle package/loader constraints appropriately.
4. **Verify artifact provenance**: version, checksum, signatures when needed, and trustworthy provenance. Successfully reading a JAR does not prove trustworthiness.
5. **Manage the lifecycle**: unregister callbacks, shut down tasks, close I/O, clear the TCCL, drop references, and use `URLClassLoader.close()` when appropriate.
6. **Have an error contract** and monitoring for plugins. A plugin exception should not corrupt host state unexpectedly; use transactional/compensation mechanisms when needed.
7. **Do not call it "safe for untrusted code"** merely because loaders are separated. This is a design for **trusted plugins that have separate dependencies**.

A custom child-first loader, if it overrides `loadClass`, also needs proper synchronization with `getClassLoadingLock`, `findLoadedClass`, and must avoid defining the same binary name twice. That is a correctness/class-identity problem, not a security sandbox.

## 11. Designing for Untrusted Plugins: Separate Processes

When the threat model includes plugins intentionally bypassing the contract, a typical architecture is:

```text
                     Host process (trusted)
                +----------------------------+
                | API gateway / plugin broker|
                | Authenticate + authorize   |
                | Input validation + limits  |
                +--------------+-------------+
                               |
                      IPC / network protocol
                               |
                +--------------v-------------+
                | Worker process (untrusted) |
                | Different OS identity      |
                | Limited filesystem mounts  |
                | Egress network policy      |
                | CPU/memory/time limits     |
                | Auditing and termination   |
                +----------------------------+
```

The host does not directly hand DB credentials, file descriptors, process handles, or host internals to the worker unless necessary. Expose to the worker **only the information and operations it needs**. For example, an image-processing plugin can receive bytes over IPC and return the processed image, without needing permission to read the entire host configuration directory.

Control layers to consider:

| Boundary/Control | Goal |
| --- | --- |
| Separate process | A worker crash/`System.exit` does not directly stop the host's JVM. |
| Separate OS user/account | File permissions restrict the worker from accessing host data. |
| Read-only/masked mounts | Prevent modifying/reading unnecessary paths. |
| Network namespace / egress rules | Prevent unintended outbound connections and reduce exfiltration. |
| CPU/memory/process limits | Mitigate DoS caused by infinite loops or unbounded allocations. |
| Wall-clock timeout + kill process | Can terminate an uncooperative worker; in-JVM thread interruption is weaker. |
| IPC validation + authorization | Prevent the worker from invoking host operations outside business permissions. |
| Logs, audit, update policy | Observe behavior, debug, and roll back when an artifact fails. |

**Note:** merely separating the process while still running under the same OS account that has full permission to read host secrets still leaves gaps in isolation. A "default" container also does not guarantee safety when granted broad host mounts, privileged mode, or open networking. The design must be based on the threat model and actual configuration.

Some systems require higher isolation levels: microVMs/hypervisors, dedicated machines, specialized sandboxes, or managed execution services. ClassLoader can still be used **inside the worker process** to help organize dependencies, while the boundary against malicious code resides at another layer.

## 12. Data Supply Risks and Plugin Verification

**A trusted source does not mean bug-free code.** A plugin with a valid signature can still contain logic bugs, dependency flaws, or inappropriate behavior. Signatures/hashes serve to verify that the artifact was distributed as expected; they do not automatically restrict runtime permissions.

A trustworthy plugin-loading pipeline might include:

- Accepting artifacts only from approved repositories/vendors.
- Pinning dependency versions and verifying checksums/signatures against an appropriate chain of trust.
- Scanning for bugs/vulnerable dependencies and signing artifacts in the supply-chain pipeline.
- Validating the plugin manifest, declared capabilities, and supported API version.
- Using an allowlist of packages/modules/entrypoints to avoid loading the wrong implementation.
- Creating a new loader per generation; not adding arbitrary JARs to the global system loader.
- Managing rollbacks if a plugin causes failures.

These steps reduce **supply and correctness** risks, but **do not turn ClassLoader into a sandbox** if a malicious artifact still slips through. Do not treat `CodeSource.location` assigned by a custom loader itself as proof of authenticity.

## 13. Common Mistakes and How to Fix Them

| Misconception | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| "A plugin has its own ClassLoader so it cannot call `Files`." | `Files` belongs to the JDK and can still be used according to process/module permissions. | Restrict via an OS/process boundary. |
| "Parent = null means Java core classes are hidden." | Bootstrap classes can still be accessed. | Understand delegation; do not use a null parent as a sandbox. |
| "Returning `new Permissions()` means no OS permissions." | PermissionCollection is not enforced without a Security Manager. | Do not rely on legacy policies to block I/O. |
| "`SecureClassLoader` is guaranteed safe because of the word Secure." | It supports domain metadata, not a modern security boundary. | Use it for source/class-loading metadata; sandbox at the process/OS level. |
| "A `CodeSource` URL is proof of a valid signature." | Metadata can be assigned manually. | Verify artifacts/signatures from the actual source. |
| "`module-info.java` does not export a package, so the plugin cannot read files." | JPMS controls package/module access, not the OS filesystem. | Distinguish encapsulation from capability enforcement. |
| "Not passing a DB client reference to the plugin is enough." | The plugin can read env/config or use network APIs directly if permitted. | Separate credentials and process permissions; enforce controlled IPC. |
| "`URLClassLoader.close()` kills the plugin." | Closing only handles loader resources per its contract; it does not terminate threads/processes. | Handle lifecycle shutdown and process termination independently. |
| "Catching `Throwable` around the plugin completely protects the host." | It does not prevent resource exhaustion, state mutation, or `System.exit`. | Use process isolation and quotas. |
| "The Security Manager can still be enabled on JDK 24 with legacy flags." | JEP 486 permanently disabled it. | Migrate to another mechanism. |
| "Using only `Thread.interrupt()` forces a plugin to stop." | Code may be uncooperative or fail to check interrupts. | Use timeouts/killing the worker process and resource limits. |
| "Scanning bytecode alone is a sandbox." | Static scanning/allowlists can miss dynamic behavior; it is not general enforcement. | Combine provenance, validation, and a system-level sandbox. |

## 14. Checklist Before Implementing a Plugin System

**For trusted plugins:**

1. Identify which packages/APIs must be defined by the host parent loader.
2. Ensure the plugin does not carry a duplicate copy of the host interface.
3. Choose the right URLClassLoader/custom loader, class source, and resource source.
4. Handle versioning, dependency conflicts, and ServiceLoader/TCCL if applicable.
5. Verify artifact provenance according to requirements.
6. Implement lifecycle management for threads, callbacks, streams, loaders, and references.
7. Test `ClassCastException`, `ClassNotFoundException`, `LinkageError`, and upgrade scenarios.

**For untrusted plugins, you must also consider:**

1. Separate process/machine boundaries and a dedicated OS identity.
2. Minimal filesystem/network permissions, without mounting host secrets.
3. CPU/memory/thread/process limits, deadlines, and a kill policy.
4. An IPC protocol with a schema, validation, authn/authz, and payload limits.
5. Keeping secrets strictly on the trusted host side whenever possible.
6. Logging, audit trail, sandbox escape threat review, and updates.
7. A trust model stating clearly which type of code is allowed into each execution tier.

A requirement to "forbid plugins from reading `/etc`" must be tested at the **filesystem/OS restriction** layer; it cannot be proven by creating a custom ClassLoader and observing that a package is not on the classpath.

## 15. Self-Check Questions

1. **Does ClassLoader create a new OS process?**  
   No. A class defined by another loader still runs inside the current JVM process.

2. **Do two loaders defining the same `com.example.Widget` share the same runtime class?**  
   No; if the defining loaders differ, the class identities differ even when the binary name matches.

3. **Why does parent delegation not stop a plugin from calling `java.nio.file.Files`?**  
   Delegation looks up and shares Java runtime classes; it does not install permissions restricting bytecode behavior.

4. **If `ProtectionDomain.getPermissions()` does not imply `FilePermission(read)`, is `Files.readString` always denied?**  
   No. Without a Security Manager, that collection creates no enforcement on its own. The demo verifies this on JDK 24.

5. **Starting from which Java release is the Security Manager permanently disabled?**  
   JDK 24 (JEP 486), following the deprecated-for-removal period starting in Java 17 (JEP 411).

6. **Does a validly signed JAR mean the plugin is restricted from network access?**  
   No. Signing pertains to provenance/integrity, not operating system permission restrictions.

7. **Do named modules with `exports`/`opens` guarantee protection against a plugin reading files?**  
   No. They control package access and reflection, not file/network policies.

8. **Does `URLClassLoader.close()` stop the plugin's threads?**  
   No. Plugin execution and thread lifecycles require separate mechanisms.

9. **If a malicious plugin needs to process data without accessing host secrets, what is a reasonable architecture?**  
   A separate worker process, restricted OS identity/rights, controlled IPC, and not passing secrets unnecessarily.

10. **Why is a plugin API containing only `getPublicGreeting` not a strong enough sandbox?**  
    Plugin bytecode can call JDK APIs directly without going through the API wrapper.

11. **If two trusted plugins need two different library versions, what should be used?**  
    Separate class loader namespaces, sharing the right API through the parent, and lifecycle management.

12. **Which documents explain the new Security Manager status?**  
    JEP 486 and the Oracle Java SE 24 Security Developer's Guide; see section 16.

## 16. Official References

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, `loadClass`, `defineClass`, delegation, protection domain.
- [Java SE 25 — SecureClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/security/SecureClassLoader.html): `CodeSource`, `getPermissions`, API Note on permissions when the Security Manager is no longer present.
- [Java SE 21 — CodeSource](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/CodeSource.html): location and certificates/signers.
- [Java SE 21 — ProtectionDomain](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/ProtectionDomain.html): domain metadata and set of permissions.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): Java 17 history.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): changes in JDK 24.
- [Oracle Java SE 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): behavior of `System`, `Policy`, `AccessController`, and migration recommendations.
- [Oracle Secure Coding Guidelines for Java SE](https://www.oracle.com/java/technologies/javase/seccodeguide.html): limitations of same-process isolation and recommendations for separate processes/OS-level controls for untrusted code.
- [JVMS 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): runtime type identity by binary name and defining loader.
