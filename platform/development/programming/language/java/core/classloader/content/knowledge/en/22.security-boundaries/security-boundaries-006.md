# SecurityManager Is a Historical Mechanism and Must Be Checked Against the JDK Version

**`java.lang.SecurityManager` is Java's historical resource access-control mechanism; it is not a recommended sandboxing tool for modern Java applications.** When reading older documentation on `ClassLoader`, plugins, `ProtectionDomain`, or `java.security.Policy`, it is very common to encounter examples that install a `SecurityManager` to restrict file-reading, socket-opening, or class-loader-creation permissions. Those examples must be understood for the **exact JDK version**, because Java has changed its policy significantly.

Key milestones:

- **JDK 8–16:** `SecurityManager` is part of the traditional security model and can be configured under specific conditions. Do not assume by default that all programs enable it.
- **JDK 17:** **JEP 411** marks `SecurityManager` along with many related APIs as **deprecated for removal**. The old mechanism still exists, but new applications should not rely on it.
- **JDK 17–23:** remains a historical compatibility period; the ability to enable/install it dynamically and warning messages **depend on the version and configuration**. Do not treat the behavior of one JDK in this range as a contract for a later JDK.
- **From JDK 24 onward:** **JEP 486** renders `SecurityManager` **permanently disabled**. It cannot be enabled at startup or have a custom manager installed at runtime. Related APIs remain for compatibility in some versions, but many methods have changed semantics; the API itself is planned to be removed in the future.

**Key takeaway of this lesson:** A class loader governs **which classes are found and defined in which namespace**; the historical SecurityManager is a mechanism for **checking operation permissions**; JPMS governs **module boundaries and API/reflective access permissions**. They do not replace one another. To run untrusted plugins, you must design **security boundaries outside the JVM or process isolation**, rather than merely creating a separate `ClassLoader`.

## 1. What Problem Did SecurityManager Historically Solve?

In historical Java applications, a system might want to run code coming from a less trusted source and restrict sensitive actions:

- Reading, writing, or deleting files on the filesystem.
- Opening network connections or listening on sockets.
- Creating subprocesses or requesting the JVM to exit.
- Creating class loaders, or modifying system properties or certain runtime configurations.
- Accessing packages, reflection, or sensitive operations according to the corresponding `Permission`s.

General idea:

```text
Code calls a sensitive API
         |
         v
Java library/runtime (in an environment with SecurityManager)
         |
         v
SecurityManager.checkPermission(permission)
         |
         +-- permission granted -> API continues
         |
         +-- permission denied -> SecurityException
```

Classes/concepts that appear in historical documentation:

| Component | Historical role |
|---|---|
| `SecurityManager` | Entry point for permission checks with `check...` methods |
| `Permission` | Represents a permission request, for example `FilePermission` or `SocketPermission` |
| `Policy` | Configuration source for granted permissions |
| `ProtectionDomain` | Associates a class/code with a domain, code source, and permissions |
| `AccessControlContext` | Permission-checking context on the call stack |
| `AccessController` | Permission checking and `doPrivileged` operations in the old model |
| `ClassLoader` | Loads/defines classes, affecting the code source and `ProtectionDomain` when using an appropriate overload |

**Key condition:** In historical JDKs, those checks take effect only when SecurityManager is actually enabled/installed and the library/runtime invokes the proper check points. The mere existence of a `Permission` or `ProtectionDomain` **does not automatically sandbox the application**.

## 2. JDK Versions and Changes to Keep in Mind

| JDK Line | SecurityManager Status | What to Understand |
|---|---|---|
| **JDK 8–16** | Traditional security mechanism still available | Configuration/installation of the manager and policies determine behavior; not enabled by default |
| **JDK 17** | **Deprecated for removal** per JEP 411 | APIs remain for compatibility; deprecation warnings and warnings upon use occur |
| **JDK 18–23** | Continuation of deprecation/support-reduction roadmap | Do not assume startup properties/defaults and `setSecurityManager` capability match JDK 17 |
| **JDK 24 and later** | **Permanently disabled** per JEP 486 | Cannot be enabled/installed; related APIs have narrowed or altered behaviors |
| **A future JDK version** | APIs may be removed | An API still compiling in one release does not guarantee it will exist in every later release |

This is a **reference overview table**, not a substitute for the migration guide of the specific vendor/runtime being deployed. In particular, the terms “deprecated” and “disabled” carry **different meanings**.

### Deprecated for removal Differs from permanently disabled

- **Deprecated for removal:** the compiler and tooling warn against using it and the API is planned for removal; in JDK 17, some historical use cases can still work when configuration allows.
- **Permanently disabled:** starting with **JDK 24**, the manager cannot be activated to enforce legacy policies, even though the `SecurityManager` API may still be present in the class library for compatibility purposes.
- **Removed:** the API is no longer present in a version; this is **not** equivalent to being “disabled” in JDK 24. When encountering bug reports, you must record the exact version and status.

**Avoid the incorrect statement:** “SecurityManager was removed in Java 17” — Java 17 **deprecated it for removal**, rather than removing it. Also avoid saying “SecurityManager still works normally in all newer JDKs because the class still exists” — from JDK 24 onward, that control mechanism **no longer functions as before**.

## 3. When Java 17 Still Allowed Configuring SecurityManager

In Java SE 17, SecurityManager could be installed at startup in supported configurations. An example from historical documentation:

```bash
# ONLY intended for studying legacy applications on JDK 17;
# do not use as a way to sandbox new plugins.
java -Djava.security.manager=default -jar legacy-app.jar
```

Another mechanism in Java 17 is declaring permission policies via a policy file and code sources/protection domains. These configurations have their own semantics and limitations; you cannot simply write a `.policy` file and assume all code in the JVM is automatically isolated.

According to the Java SE 17 API, `java.security.manager` accepts values such as `allow` and `disallow` along with historical values that enable the manager. For example:

- `disallow`: does not install a manager at startup and prevents dynamic installation, causing `System.setSecurityManager(...)` to throw `UnsupportedOperationException`.
- `allow`: does not install a manager at startup, but permits attempting dynamic installation according to the JDK 17 contract and the active policy.
- `default` (or the corresponding historical configuration): can install the default manager on JDK 17 startup.

**Do not carry over JDK 17 property rules directly to JDK 24+.** On JDK 24, an option attempting to enable/allow SecurityManager at startup is a **JVM initialization error**, not merely a deprecation warning.

### JDK 24+: Enabling SecurityManager Is a Startup Error

Example command on Bash:

```bash
java -Djava.security.manager=allow -version
```

On **Windows PowerShell 5.1**, you should enclose the `-D...=...` argument in quotes to avoid how the shell parses the equals sign:

```powershell
java '-Djava.security.manager=allow' -version
```

With OpenJDK 24, the JVM fails to start and the main message includes:

```text
Error occurred during initialization of VM
java.lang.Error: A command line option has attempted to allow or enable the Security Manager. Enabling a Security Manager is not supported.
```

These are the **two main lines of content**; the stack trace and `System.java` line numbers vary by patch release/vendor. The command terminates with an error code (in the OpenJDK 24 test, **exit code 1**). Do not rely on that exit code/message as a business-logic handling contract; it demonstrates that the feature can no longer be enabled.

In JDK 24+, `System.setSecurityManager(...)` always throws **`UnsupportedOperationException`**. Do not design new programs to call it and catch the error to activate a fallback sandbox.

## 4. Runnable Java 17+ Example: Checking Version, Manager, and Host API

The example below illustrates three things that should not be conflated:

1. Checking the **actual Java runtime version**, not just the target version the source was compiled for.
2. Observing whether a SecurityManager is currently installed — **without trying to install one yourself**.
3. A host API can proactively reject an operation per its business contract **without depending** on SecurityManager.

Save a file named **`SecurityBoundaryDemo.java`**:

```java
public final class SecurityBoundaryDemo {

    interface HostApi {
        String readSetting();
        void changeSetting(String value);
    }

    static final class ReadOnlyHostApi implements HostApi {
        @Override
        public String readSetting() {
            return "safe-config";
        }

        @Override
        public void changeSetting(String value) {
            throw new SecurityException(
                    "Host API forbids this operation");
        }
    }

    @SuppressWarnings("removal")
    static boolean oldManagerInstalled() {
        return System.getSecurityManager() != null;
    }

    public static void main(String[] args) {
        int feature = Runtime.version().feature();

        System.out.println("Java feature: " + feature);
        System.out.println("SecurityManager present: "
                + oldManagerInstalled());

        System.out.println("Status: " + (feature >= 24
                ? "permanently disabled"
                : "legacy, check runtime configuration"));

        HostApi api = new ReadOnlyHostApi();
        System.out.println("Read via host API: "
                + api.readSetting());

        try {
            api.changeSetting("new-config");
            System.out.println("Unexpected host API success");
        } catch (SecurityException expected) {
            System.out.println("Write via host API: denied");
        }
    }
}
```

Compile on Java 17+:

```bash
javac --release 17 SecurityBoundaryDemo.java
java SecurityBoundaryDemo
```

Verified output on **OpenJDK 24**, compiled targeting **Java 17**:

```text
Java feature: 24
SecurityManager present: false
Status: permanently disabled
Read via host API: safe-config
Write via host API: denied
```

If run on **JDK 17–23**, the `Java feature` and `Status` lines will differ; `SecurityManager present` may change depending on whether a manager is enabled. The example **does not guarantee identical stdout across all JDKs**. You should also not guess the feature version when using a customized vendor runtime: observe the value printed by the program.

### Why Is @SuppressWarnings("removal") Present?

`System.getSecurityManager()` has been marked deprecated for removal since Java 17. The annotation in the example is solely meant to **keep the compiler output clean for compatibility checks**. It does **not** make the method a recommended API again, does not alter runtime behavior, and **must not be viewed as a migration solution**.

In new production code, if you are not integrating any legacy code, it is best **not to call `getSecurityManager()` at all**. Focus on real security boundaries designed by the application/infrastructure.

### Why Is ReadOnlyHostApi Not a Sandbox?

The `changeSetting` method proactively throws `SecurityException`. This is merely a **restriction imposed by the host API on callers that abide by the contract**.

An arbitrary plugin running in the **same JVM** can still attempt to call `java.nio.file.Files`, `java.net.Socket`, or other APIs from its own code. `ReadOnlyHostApi` cannot block those access paths simply because it throws an exception in one method.

Therefore, **do not use a plain API wrapper as an execution boundary against malicious code**. It is useful for trusted applications/plugins and least-authority design at the business layer; for untrusted code, **OS/process isolation** is required.

## 5. ClassLoader and SecurityManager Answer Two Different Questions

`ClassLoader` primarily answers: **Which class is found/defined, by which loader, and under which namespace?**

The historical `SecurityManager` answers: **Is this sensitive operation permitted by policy in the currently executing context?**

For example:

```text
CustomClassLoader
    |
    +--> findClass("plugin.Worker")
    |       |
    |       +--> defineClass(bytecode)
    |                 |
    |                 +--> runtime class identity
    |
    +--> loadClass("shared.api.Plugin")
            |
            +--> delegate to parent
```

Having the loader create a separate namespace for `plugin.Worker` does not automatically restrict file-reading or subprocess-invocation permissions. Even when a plugin resides in its own loader, its code still runs in the **same process** unless another boundary is in place.

| Mechanism | What Does It Do Well? | What It Cannot Guarantee on Its Own |
|---|---|---|
| Parent delegation | Sharing platform types and shared APIs | Does not guarantee that a plugin cannot access the filesystem/network |
| Separate defining ClassLoader | Class identity, dependency isolation, loader lifecycle | Not an OS/runtime permissions sandbox |
| `ProtectionDomain`, `CodeSource` | Recording provenance/metadata and supporting corresponding mechanisms | Does not automatically make a class untrusted/sandboxed in modern JDKs |
| Historical SecurityManager | Certain permission checks when enabled in supported JDKs | Not a usable security boundary from JDK 24 onward |
| JPMS `exports` / `opens` | Controlling access between named modules and reflection/package resources | Does not block the filesystem, network, or all native APIs |
| Process/container/OS policy | Can enforce permissions at appropriate OS boundaries | Requires real configuration; not automatically secure just by running in a container |

**A very common misconception:** “One plugin, one loader” can allow multiple versions of `com.vendor.Library` to coexist side by side, but it does not mean each plugin has its own set of OS permissions.

## 6. ProtectionDomain, CodeSource, and Permission Still Appear — Understanding the Right Context

Long-standing custom loader examples often write:

```java
ProtectionDomain domain =
        new ProtectionDomain(codeSource, permissions, loader, null);

Class<?> type = defineClass(
        binaryName, bytes, 0, bytes.length, domain);
```

This is an **illustrative snippet**; it requires actual variables and imports inside a `ClassLoader` subclass.

In the historical design, `ProtectionDomain` could carry a `CodeSource` (URL, certificates) and a collection of granted `Permission`s; SecurityManager/AccessController used that context to evaluate various access checks.

However:

- **Creating a ProtectionDomain does not automatically enable SecurityManager**.
- Passing a `PermissionCollection` to `defineClass` **does not guarantee** that JDK 24 enforces sandboxing on each Java API operation.
- In JDK 24, many APIs that previously served SecurityManager have “degraded” behavior; for example, per Oracle JDK 24/25 guidance, `Policy` is no longer used to grant execution permissions as in the old model.
- `ProtectionDomain.getCodeSource()` remains useful in some provenance/diagnostics tasks, but provenance **is different from** authorization.
- Obtaining the code source URL does not prove the bytecode is trustworthy, does not verify signatures, and does not replace supply-chain protection.

When reading older source code/frameworks containing `SecureClassLoader`, `ProtectionDomain`, or permission checks, **do not immediately conclude that they are as secure as an older deployment on JDK 8/11**. You must examine the runtime version and the other protective layers of the deployment.

## 7. AccessController.doPrivileged and checkPermission No Longer Mean Permission Control

In the historical model, `AccessController.doPrivileged(...)` commonly appeared in library code that needed to perform a privileged operation in a controlled manner within a stack-based permission-checking context.

Old example:

```java
// Legacy pattern to recognize when reading code; not recommended for new code.
return AccessController.doPrivileged(
        (java.security.PrivilegedAction<String>)
        () -> System.getProperty("example.setting"));
```

This is an **illustrative in-method snippet** with the `AccessController` type imported; it is not a standalone program.

**On JDK 24+:**

- The remaining `AccessController.doPrivileged(...)` variants **execute the action directly**, just as when no SecurityManager was present in older versions.
- Under the updated specification, `AccessController.checkPermission(...)` will **always throw `AccessControlException`**.
- `SecurityManager.check...` variants may **always throw `SecurityException`** in the degraded API.
- `System.getSecurityManager()` always returns **`null`**.
- `System.setSecurityManager(...)` always throws **`UnsupportedOperationException`**.

**Do not misinfer in either direction:**

1. Because `doPrivileged` still runs, that does **not** mean the old security policy is still in effect.
2. Because `checkPermission` throws an exception, that does **not** mean the entire system is protected by policy; directly calling a legacy API whose semantics have changed does not reflect filesystem/network access control.

Each API has its own behavior. Do not generalize on your own that “all SecurityManager APIs are no-ops”; in JDK 24, some methods are no-ops, some return `null`, and some always throw an exception.

## 8. SecurityException Does Not Prove SecurityManager Is Enabled

`SecurityException` is a common Java exception type used for many constraints that **do not depend** on having an installed SecurityManager.

Example in class loading:

```java
// Inside a custom ClassLoader subclass:
return defineClass("java.fake.Reserved", bytes, 0, bytes.length);
```

This is an **illustrative snippet** (requiring valid class-file bytes). `ClassLoader#defineClass` has its own rules: an ordinary custom/application loader is not allowed to define a class whose name starts with `java.`. A `SecurityException` can occur **even when `System.getSecurityManager() == null`**.

Other causes to distinguish:

- Inconsistent signer certificates when the same loader defines classes in a package.
- A custom library/framework throwing `SecurityException` itself according to its own policy.
- An API/loader inspecting the namespace/package/bytecode/environment and rejecting it.
- On a historical JDK, SecurityManager genuinely denying a Permission.

Therefore, diagnosis must inspect the **stack trace, root cause, and JDK version**, not just the name `SecurityException`.

### A Short Comparison Table

| Symptom | Definitely Caused by SecurityManager? | What to Check |
|---|---|---|
| `ClassNotFoundException` | No | Name, classpath/module path, defining loader, parent delegation |
| `SecurityException: Prohibited package name: java...` | No | `ClassLoader#defineClass` rule for `java.*` |
| `IllegalAccessError` | No | Java access rules, runtime package, and module access |
| `InaccessibleObjectException` | No | Reflection/JPMS `opens` and caller module |
| `UnsupportedOperationException` in `System.setSecurityManager` (JDK 24+) | Related to disabled legacy API | Upgrade the design; do not look for a flag to re-enable it |
| Startup error with `-Djava.security.manager=allow` on JDK 24+ | Related to disabled mechanism | Remove the legacy configuration and replace it with another isolation approach |

Do not “fix” these errors by installing a new SecurityManager. That does not resolve class/module identity, and from JDK 24 onward it is not feasible either.

## 9. JPMS Is a Different Boundary, Not a Plugin Sandbox

Java 9+ provides the **Java Platform Module System (JPMS)**, declared as:

```java
module host.api {
    exports host.api;
}
```

```java
module plugin.alpha {
    requires host.api;
}
```

These are **two illustrative `module-info.java` files in two different modules**, not combined into a single source file.

JPMS helps:

- Organize dependencies via `requires`.
- Specify which public packages are accessible from other modules using `exports`.
- Govern reflection/deep access via `opens`.
- Detect certain module graph/split-package conflicts.
- Manage plugin modules in a `ModuleLayer` when the architecture fits.

However, if plugin code in `plugin.alpha` runs **in the same JVM process**, JPMS does not automatically prevent it from calling filesystem/network APIs accessible to that module. A valid module descriptor **is not a SecurityManager-style resource policy**.

### A ClassLoader Does Not Automatically “Open” Every Package of a Module

A custom loader can locate class files, yet invoking reflection on private members of a named module is still subject to `opens` rules. Conversely, adding `--add-opens` can grant a scope of reflective access, **without** turning a custom loader into a sandbox or granting an independent set of file permissions.

Therefore, three questions must be kept separate:

1. Which loader finds/defines the class?
2. Does the caller module have access to the package/member?
3. Is the code/process permitted to use operating system resources?

These three answers belong to different control layers.

## 10. What Modern Java Applications Should Do Instead of SecurityManager

### A. Trusted Code: Use Explicit Contracts and Application-Layer Controls

If plugins are **trusted and released by the same organization**, design:

- A shared SPI/DTO with a small API and clear versioning.
- A host API providing only the operations plugins genuinely need.
- Access checks at the service boundary (tenant, user, RBAC, quota, audit).
- Input validation and authentication/authorization at entry points.
- Secrets not exposed through global static fields/system properties.
- Consistent logging and exception handling.

This is a clean and testable architecture, but **it is not a boundary against malicious plugins when sharing the same process**. Arbitrary code can still call other APIs if the environment permits.

### B. Untrusted Plugins: Process Isolation

If you need to run untrusted customer or third-party code, consider:

```text
Host Process
  |
  | validated RPC/IPC messages
  v
Plugin Worker Process
  |
  +-- separate OS user/permissions
  +-- restricted filesystem mounts
  +-- restricted network policy/egress
  +-- CPU/memory/process quotas
  +-- short-lived credentials
  +-- timeout and kill/restart
```

Measures can include **containers**, VM isolation/hypervisors, Linux namespaces/seccomp, Windows sandboxes/job objects, or appropriate macOS mechanisms. No single technology is automatically secure by name alone; actual permissions must be configured and tested.

Design the host↔plugin interface using simple data or schemas (JSON, Protobuf...) to avoid exposing internal object references and to make resource limits easier to enforce.

### C. Least Privilege at the OS/Cloud Boundary

- Do not run the plugin process with administrator/root privileges unless necessary.
- Mount only the directories that must be read/written; separate read-only and writable storage.
- Restrict network egress, DNS, and socket/listening ports as required.
- Use short-lived credentials with narrow scope.
- Limit CPU, memory, process/thread counts, and execution time.
- Isolate secrets and log sensitive data in a controlled manner.
- Verify signatures/artifact provenance, perform dependency scanning, and enforce an update policy.

**SecurityManager is no longer the place to implement those requirements on Java 24+.**

## 11. When Maintaining Legacy Frameworks/Plugins

Some code written in JDK 8/11 may do the following:

```java
@SuppressWarnings("removal")
static void legacyCheck() {
    SecurityManager sm = System.getSecurityManager();
    if (sm != null) {
        sm.checkPermission(
                new java.io.FilePermission(
                        "config.properties", "read"));
    }
}
```

This is an **illustrative legacy snippet**, not an authorization measure for new code.

- On JDK 17 with a real SecurityManager enabled, the check can deny the operation according to the active policy.
- On JDK 24+, `System.getSecurityManager()` always returns `null`, so the `if` branch will not execute. There is no permission gate in that code snippet.
- If a library calls `AccessController.checkPermission` unconditionally on JDK 24+, it can **throw an exception unconditionally**, breaking the program in a different way.
- For code containing `doPrivileged`, the behavior may still be to run the action immediately, without the old stack-based permission-gating model.

**The fact that legacy code still compiles/runs does not prove the security model remains intact.** You must verify the exact effect of each API on the target JDK.

### A Practical Migration Plan

1. **Confirm the current and target runtimes:** `java -version`, JDK vendor, patch release, startup options.
2. **Locate historical configurations:** `-Djava.security.manager`, `-Djava.security.policy`, policy files, custom `SecurityManager` classes.
3. **Locate deprecated APIs:** `System.getSecurityManager`, `System.setSecurityManager`, `SecurityManager`, `AccessController`, `Policy`, and `Permission` checks.
4. **Classify intent:** was the code truly enforcing permissions, merely checking presence, or using `doPrivileged` for compatibility?
5. **Define the threat model:** untrusted source code, resource sandboxing, preventing `System.exit`, restricting filesystem/network, or solely business-level permissions?
6. **Choose replacement mechanisms:** process/OS boundaries for untrusted code; authorization/capability APIs for trusted code; bytecode instrumentation if the use case is intercepting APIs in a controlled environment, with its own limitations.
7. **Test on JDK 24+:** remove prohibited startup flags; test code paths that were formerly secured.
8. **Clean up deprecated calls:** do not merely suppress warnings; replace broken assumptions and update tests/runbooks.
9. **Perform post-migration security checks:** verify that no unintended permissions were opened and no bypass is created when `getSecurityManager() == null`.
10. **Track upcoming releases:** the APIs may be removed in the future, so avoid accumulating code that runs only for temporary compatibility.

### Commands to Aid Inventory

```bash
java -version
javac -version

# Scan compiled classes/JARs to detect deprecated APIs
# (flags/support depend on the tool version).
jdeprscan --release 17 path/to/application.jar
```

The `jdeprscan` command is a **diagnostic example**; replace `path/to/application.jar` with your actual artifact. Results depend on the scanned file and the JDK providing the tool. You should not scan just one JAR and conclude that every dynamic/reflection use of SecurityManager has been found; combine this with source/config searches and testing.

Do not use `jdeps --jdk-internals` as a way to check all deprecated SecurityManager APIs; it serves a different purpose (analyzing usage of internal JDK APIs).

## 12. Can a Java Agent Be Used to Block System.exit?

One use case that previously relied on SecurityManager was preventing plugins from calling `System.exit(int)`. According to Oracle documentation for JDK 24+, once SecurityManager is disabled, **agent/bytecode instrumentation** can be used in cases where calls need to be controlled:

```text
Class loading
    |
    +--> ClassFileTransformer
             |
             +--> find bytecode calling System.exit(int)
             +--> replace with code throwing RuntimeException
    |
    +--> JVM defines the transformed class
```

This is a tooling model, not a general-purpose sandboxing solution.

**Warning:** Instrumentation can be bypassed through other invocation paths (native code, reflection, method handles, alternate APIs, attach/agent configuration, dynamic class loading...) if the threat model is not fully addressed. If plugin code is genuinely **untrusted**, an agent blocking a few methods **does not replace OS isolation**.

When you need to uphold the guarantee that “a plugin cannot terminate the host JVM,” the robust solution is usually to **run the plugin in a separate process** so that process-level actions do not bring down the entire host.

## 13. Notes on ClassLoader Itself and Bytecode Security

`ClassLoader` is useful for namespaces and plugin lifecycles, yet the JVM still enforces **intrinsic constraints**:

- Not every application loader is allowed to arbitrarily call `defineClass` in the `java.*` namespace.
- The JVM verifier/linker checks class-file format and type safety according to JVM rules.
- Runtime class identity is based on **(binary name, defining loader)**.
- Runtime package identity is based on **(package name, defining loader)**, affecting package-private access.
- JPMS `exports`/`opens` and module resolution still apply.
- Security-sensitive native libraries/OS privileges have their own policies.

These rules remain important in JDK 24 **without needing SecurityManager**. However, the existence of the verifier, the `java.*` restriction, or module encapsulation **does not turn ClassLoader into a file/network permissions sandbox**.

For example, `ClassLoader#defineClass` may throw `SecurityException` when a custom loader attempts to define `java.fake.Reserved`; that event does not indicate that the JDK 8 permission policy has returned.

### Conclusion on Defensive Layers

```text
Untrusted plugin code
    |
    +--> ClassLoader: namespace/classes/delegation
    |
    +--> JVM verifier, linking, type identity
    |
    +--> JPMS: modules/API/reflection access
    |
    +--> Host API authorization: business contract
    |
    +--> Process/OS/cloud controls: actual security boundary
```

These protective layers **complement** one another, but they do not serve the same role. On modern JDKs, **do not place SecurityManager in the diagram as an active enforcement step**.

## 14. Common Misconceptions

| Misconception | Correction |
|---|---|
| “Java 17 removed SecurityManager.” | Java 17 **deprecated it for removal**; the mechanism was not removed at that time. |
| “JDK 24 still has the SecurityManager class, so it can still be enabled.” | JDK 24 **permanently disabled** it; both startup and installation are blocked. |
| “Changing `java.security.manager=allow` is enough.” | JDK 24 treats a flag allowing/enabling the manager as a **VM initialization error**. |
| “SecurityManager is a Java feature enabled by default.” | You should not assume so, even in older JDKs. |
| “A separate ClassLoader sandboxes a plugin.” | It isolates runtime types/namespaces, **not** all OS permissions. |
| “Having a `ProtectionDomain` means the file permission policy will work.” | Permission enforcement depends on the mechanism/runtime; JDK 24 does not use SecurityManager as before. |
| “If `AccessController.doPrivileged` still runs, the sandbox is still running.” | In JDK 24+, `doPrivileged` runs the action directly; it does not prove permission gating. |
| “`AccessController.checkPermission` throwing an exception means the sandbox is secure.” | JDK 24 may throw unconditionally; it does not replace real resource controls. |
| “JPMS `exports` and `opens` protect the plugin's filesystem.” | They manage module/package access, not OS permissions. |
| “SecurityException always comes from SecurityManager.” | Many APIs have independent checks, including `ClassLoader#defineClass`. |
| “An agent blocking System.exit is a complete sandbox.” | Intercepting a few APIs is insufficient for a malicious-code threat model. |
| “Simply suppressing deprecation warnings completes the migration.” | You must replace the security model and tests, not just change compiler options. |

## 15. Self-Check Questions

**1. What did JDK 17 do with SecurityManager?** Marked it **deprecated for removal** per JEP 411; it did not remove it immediately.

**2. Starting from which version is SecurityManager permanently disabled?** From **JDK 24**, per JEP 486.

**3. What does `System.getSecurityManager()` return on JDK 24+?** `null`, per the new API behavior.

**4. Can `System.setSecurityManager(...)` on JDK 24+ install a manager if configured with `allow`?** No. The method throws `UnsupportedOperationException`; a flag allowing/enabling the manager at startup causes a JVM initialization error.

**5. Does `AccessController.doPrivileged` escalate privileges on JDK 24?** No. It executes the action as when no SecurityManager is present, without providing the old permission-based escalation mechanism.

**6. Can `AccessController.checkPermission(...)` on JDK 24 be used to replace an internal permission service?** No. This API has altered behavior and may throw `AccessControlException` unconditionally; you need to design your own authorization.

**7. Is a plugin with its own ClassLoader automatically blocked from reading files?** No. A loader manages class loading/identity, not an OS sandbox.

**8. Is `ProtectionDomain` enough to forbid a plugin from opening sockets?** No, especially with SecurityManager disabled; an actually enforced runtime/OS boundary is required.

**9. Does a `SecurityException` on `defineClass("java.fake.X", ...)` prove SecurityManager is enabled?** No. The `java.*` namespace rule of `defineClass` is independent of any installed manager.

**10. Do JPMS and SecurityManager have the same responsibility?** No. JPMS addresses module/API access; the historical SecurityManager targeted permission checks for certain resource operations.

**11. When migrating from Java 8/11 to JDK 24+, what should you look for?** Startup flags/policy files, custom managers, calls to `get/setSecurityManager`, `AccessController`, `Policy`, and the protective layers expected to remain effective.

**12. What is a safer way to run untrusted plugins on modern JDKs?** Isolation via process/container/OS policy with least privilege, resource limits, an IPC contract, and threat-model testing.

## 16. Official Documentation and Version Milestones

- **JEP 411 — Deprecate the Security Manager for Removal** (associated with JDK 17): https://openjdk.org/jeps/411
- **JEP 486 — Permanently Disable the Security Manager** (associated with JDK 24): https://openjdk.org/jeps/486
- **Java SE 17 API — `SecurityManager`**, noting `@Deprecated(forRemoval=true)` and legacy behavior: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html
- **Java SE 17 API — `System.getSecurityManager` and `System.setSecurityManager`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html
- **Oracle JDK 25 Security Developer’s Guide — The Security Manager Is Permanently Disabled** (describing behavior changes effective from JDK 24): https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html
- **Oracle JDK 25 Migration Guide — Migrating from JDK 8 to Later JDK Releases**: https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html
- **Java SE 17 API — `ClassLoader`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 API — `ProtectionDomain` / `AccessController`** (solely for understanding legacy code): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/AccessController.html

**Remember:** **SecurityManager is a historical mechanism that must be interpreted according to the JDK version**. JDK 17 **deprecated it for removal**, whereas **JDK 24+ permanently disables it**. `ClassLoader`, `ProtectionDomain`, and JPMS each still have their own purpose, but **they do not replace SecurityManager's resource-permission sandbox**. When the problem involves untrusted plugins, design process/OS isolation and real permission controls from the start.
