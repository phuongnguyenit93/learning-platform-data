# Security Manager Deprecated for Removal in JDK 17 and Permanently Disabled in JDK 24

**The Java Security Manager** previously provided a permission-checking model using `Permission`, `Policy`, `AccessController`, and `SecurityManager.check...` methods. Some legacy applications used it to restrict file, network, or sensitive actions by dynamically loaded code. However, that approach is no longer a suitable foundation for modern Java security.

Two milestones must be distinguished **precisely**:

- **JDK 17 — JEP 411:** `SecurityManager` and related APIs were **marked deprecated for removal** (slated to be removed in a future Java release). This is **not** when the API was deleted from the JDK or when the Security Manager was permanently disabled.
- **JDK 24 — JEP 486:** The Security Manager **is permanently disabled**. It cannot be enabled from startup flags, cannot be installed via `System.setSecurityManager(...)`, and related security APIs have modified behavior. **The API still exists in JDK 24, but is scheduled for removal in a future version.**

**For runtime extensibility:** If an application allows running plugins, scripts, dynamically compiled Java code, or classes loaded via `URLClassLoader`, **you cannot rely on the Security Manager as an isolation boundary for untrusted code on JDK 24**. Instead, you need an explicit business-authorization model and, for untrusted code, **process/container/VM isolation combined with OS-level and communication-channel permission controls**.

This lesson moves from historical context, concrete API changes, and Java 17/24 examples to inventorying and safely migrating your architecture.

## 1. What Did the Security Manager Previously Control?

In the legacy model, Java had related classes such as:

| Component | Previous role |
|---|---|
| `java.lang.SecurityManager` | Policy checkpoint when Java libraries performed certain sensitive operations |
| `java.security.Permission` | Represents a type of permission such as reading files or opening network connections |
| `java.security.Policy` | Supplies the set of permissions applied to code/code sources |
| `java.security.ProtectionDomain` | Aggregates protection-domain information for a class, code source, and permissions |
| `java.security.AccessController` | Performed certain permission checks and actions within a security context |
| `java.security.AccessControlContext` | Represents a permission-checking context |
| `java.security.AccessController.doPrivileged(...)` | Previously involved in evaluating stack-based access control |

A conceptual diagram of the **historical model**:

```text
Plugin / script / Java library
              |
     calls sensitive operation
              |
              v
    Java Platform API
              |
    [if Security Manager is enabled
     and the API actually invokes the check]
              |
              v
SecurityManager / AccessController
              |
              v
   Policy + Permission + context
       /                    \
    allow                  deny
      |                      |
 operation proceeds    SecurityException
```

This is merely a diagram of the mechanism during the era when the Security Manager was supported. It **does not mean every operation of every library or native code passed through the Security Manager**, and "having a Security Manager" must not be treated as a guarantee of complete isolation. Effectiveness depended on which APIs performed checks and the privileges of executing code.

For untrusted code, two major issues emerge:

1. The Security Manager operated **inside the same JVM** and had to maintain a very broad checking model, struggling to cover all new APIs and access paths outside the JDK.
2. Actual code privileges were also affected by the OS, native libraries, process identity, JVM configuration, and already-privileged services.

Deprecating and then disabling it is a decision at the **Java platform** level; it does not mean Java dropped cryptography, TLS, or authentication APIs. `JCA`, `JSSE`, `KeyStore`, OS permission controls, and application-level authorization mechanisms still exist and serve different purposes.

## 2. Timeline: Deprecated in JDK 17 vs. Disabled in JDK 24

| Stage | Security Manager status | Practical consequence |
|---|---|---|
| Before JDK 17 | Security Manager was the legacy mechanism with policy/permission APIs | Some applications installed a manager or used policy files |
| **JDK 17** | **JEP 411**: deprecated for removal | Code using this API receives deprecation warnings; some transitional ways to enable the manager remained supported per JDK release rules |
| JDK 17–23 | Transition period, legacy support restricted and warned; dynamic enabling behavior depended on version/configuration | Inventory and remove dependencies; do not build new sandbox features on the legacy API |
| **JDK 24** | **JEP 486**: permanently disabled | Cannot enable/install a manager; legacy calls have newly specified behavior |
| Future releases | Security Manager APIs are planned for **removal** | Code still referencing those type/method names risks failing to compile |

### 2.1. What Exactly Is "Deprecated for Removal"?

In the Java 17 API, `java.lang.SecurityManager` is annotated:

```java
@Deprecated(since = "17", forRemoval = true)
public class SecurityManager {
    // Illustrative annotation declaration.
}
```

This is an **annotation illustration**, not the full JDK class declaration and not for use as application code. The meaning of `forRemoval = true`: the API has been marked for future removal, and compilers/tools may emit warnings at usage sites. It does **not** mean the class vanishes immediately or that every JDK 17 program calling it fails to compile.

In JDK 17, there was still a period allowing the Security Manager to be enabled under appropriate historical conditions while emitting warnings. Those transitional mechanisms are **not a durable contract** to carry forward onto Java 24.

### 2.2. What Exactly Is "Permanently Disabled"?

Starting in JDK 24:

- **Cannot enable Security Manager at startup.** Flags attempting to enable or allow it cause the JVM **to fail to start**, rather than merely printing a warning.
- **Cannot install Security Manager at runtime.** `System.setSecurityManager(...)` throws `UnsupportedOperationException`, even when passing `null`.
- `System.getSecurityManager()` always returns `null`.
- Many methods in legacy security-policy classes return default values, pass through calls, or throw exceptions under JEP 486 rules; they no longer enforce stack-based permission checks as before.
- JDK APIs that previously consulted the Security Manager to potentially block sensitive operations now generally **do not perform that Security Manager check**. Thus, keeping a `Policy` or calling `doPrivileged` in an application creates no isolation.
- The system policy file `$JAVA_HOME/conf/security/java.policy` is removed from JDK 24's configuration; related Security Manager policy properties are no longer supported as before.

**Do not confuse disabled with removed:** An API may still compile while having no-op or altered behavior. That is more dangerous than an obvious compile error if an application assumes "no exception thrown" means permissions are still being checked.

## 3. Table of Key API Behaviors on JDK 24

| API or mechanism | Behavior from JDK 24 | Impact during upgrade |
|---|---|---|
| `System.getSecurityManager()` | Always `null` | `if (sm != null)` branches never execute |
| `System.setSecurityManager(...)` | Always throws `UnsupportedOperationException` | Cannot install a custom manager, even to clear it with `null` |
| Startup `-Djava.security.manager=allow` or similar enable flags | JVM reports an initialization error and exits | No more opt-in Security Manager mode |
| `AccessController.doPrivileged(...)` | Executes the action directly as if no Security Manager exists | Creates no privilege restriction or sandbox |
| `AccessController.checkPermission(...)` | Throws `AccessControlException` | No longer a valid business permission-checking mechanism |
| `SecurityManager.check...(...)` | Legacy check methods throw `SecurityException` when called directly | Do not infer that the JDK still invokes them automatically to guard filesystem/network |
| `java.security.Policy.setPolicy(...)` | Throws `UnsupportedOperationException` | Cannot swap policies to activate legacy controls |
| `Policy.getPolicy()` | Policy whose permission checks grant no permissions | Does not mean the JDK is denying OS operations based on the policy |
| JDK calls that used to consult Security Manager | No longer invoke legacy-model checks | Need a different control policy at the trust boundary |

**Subtle detail:** Calling `AccessController.checkPermission(...)` or `SecurityManager.checkPermission(...)` directly can **throw an error even when an ordinary file read still succeeds**. Therefore, you cannot use the outcome of a manual check method to conclude that the JVM enforces a Security Manager policy across all APIs.

### 3.1. Why Can Legacy Branches Silently Keep Running?

A legacy code pattern:

```java
// Legacy code example; NOT recommended for new applications.
@SuppressWarnings("removal")
static void oldCheck() {
    SecurityManager manager = System.getSecurityManager();
    if (manager != null) {
        manager.checkRead("/opt/data/report.csv");
    }
}
```

This is an **illustrative method**, not a standalone program. On JDK 24, `System.getSecurityManager()` is always `null`, so `manager.checkRead(...)` **is not called**. Code keeps running without the corresponding permission check. Similarly, snippets that only wrap logic in `AccessController.doPrivileged(...)` create no privilege separation; the action simply executes.

Do not "fix" the snippet above by removing the condition and calling `new SecurityManager().checkRead(...)`: invoking a manual check on JDK 24 does not turn it into a policy filter and may simply throw unconditionally. **The proper solution is redesigning permissions at the host/OS layer.**

### 3.2. Startup Options on JDK 24

The following command **must no longer appear in startup procedures**:

```bash
java -Djava.security.manager=allow -jar app.jar
```

Starting in JDK 24, when the JVM is asked to enable or allow the Security Manager, the result is a VM initialization failure, for example the start of the message:

```text
Error occurred during initialization of VM
java.lang.Error: A command line option has attempted to allow or enable the Security Manager. Enabling a Security Manager is not supported.
```

This is an illustrative message excerpt, omitting the stack trace which can vary by JDK build. Monitoring systems must treat this as a **startup failure**, rather than retrying indefinitely with the same config or assuming it is a suppressible warning.

## 4. Java 17+ Example to Probe Legacy Behavior on JDK 24

To observe the changed behavior accurately, the following program does two things: reads the state and **attempts to call the legacy manager-setter API**. This is strictly **migration-testing code**, not code to put into production execution paths.

Save as **`LegacySecurityManagerProbe.java`**:

```java
public final class LegacySecurityManagerProbe {

    @SuppressWarnings("removal")
    public static void main(String[] args) {
        System.out.println(
                "feature=" + Runtime.version().feature());

        System.out.println("manager="
                + (System.getSecurityManager() == null
                   ? "null" : "present"));

        try {
            System.setSecurityManager(null);
            System.out.println("set=accepted");
        } catch (UnsupportedOperationException exception) {
            System.out.println("set=UnsupportedOperationException");
        }
    }
}
```

Compile targeting Java 17 with a JDK supporting `--release 17`, then **run with JDK 24**:

```bash
javac --release 17 LegacySecurityManagerProbe.java
java LegacySecurityManagerProbe
```

Verified stdout on **JDK 24**:

```text
feature=24
manager=null
set=UnsupportedOperationException
```

**How to read the output:**

- `feature=24` comes from `Runtime.version().feature()`: indicates the running major feature version. When running on another Java version, this number changes.
- `manager=null`: on JDK 24, no active Security Manager exists. This does not mean the JVM enabled a default policy blocking all actions.
- `set=UnsupportedOperationException`: `System.setSecurityManager(null)` is rejected. This is a behavior change from JEP 486, not an authorization error from a specific policy file.
- `@SuppressWarnings("removal")` only suppresses warnings when **compiling the legacy probe example**; it does not enable the Security Manager, does not change runtime behavior, and **should not** be used to hide technical debt in production code.

**Scope of applicability:** this example is only meaningful while the legacy APIs are still present, such as on JDK 17–24. When run on JDK 17–23, `System.setSecurityManager(null)` may behave according to that version's rules/enabling flags, so **stdout matching JDK 24 is not expected there**. Once the APIs are removed in a future release, sources referencing them will need updating rather than continuing to use the probe.

## 5. Why Does This Matter Especially for Plugins, Scripts, and Dynamically Compiled Code?

### 5.1. `ClassLoader` Is Not a Sandbox

`URLClassLoader`, custom class loaders, and `ModuleLayer` help the JVM manage **class namespaces, loader relationships, module readability, and lifecycles**. They do not automatically create quotas for filesystem, network, process creation, or OS permissions.

If a plugin is loaded into the same JVM and can call host Java APIs, it generally runs under the application's **process identity**. Creating a child class loader alone does not stop a plugin from:

- Reading files the Java process has permission to read.
- Sending connections to endpoints the Java process is permitted by the network to reach.
- Calling `System.exit(...)` or spawning CPU-consuming threads, absent independent controls.
- Accessing services/secrets exposed by the process's classpath and capabilities.
- Using other Java/native paths outside the plugin interfaces the application intended to publish.

**JPMS `exports`/`opens` and class loader delegation are not equivalent to OS permission policies.** These tools are useful for organizing modules and managing compatibility, not as a replacement for the Security Manager to execute untrusted code.

### 5.2. `ScriptEngine`, `JShell`, and Runtime Compilers Do Not Guard Access Permissions

APIs such as `javax.script.ScriptEngine`, `jdk.jshell.JShell`, and `javax.tools.JavaCompiler` serve **script evaluation, interactive code, and compilation**. They do not inherently guarantee that user-supplied code can only read what is permitted.

- `JavaCompiler` produces bytecode; it does not make that bytecode safe to run.
- `ScriptEngine` may expose Java host objects/class lookup depending on the engine. `Bindings.put("api", facade)` only defines objects the host proactively provides; it does not prove the engine blocks other host interop paths.
- `JShell` is a snippet evaluation/execution tool and must not be treated as a permission filter replacing the Security Manager.
- A plugin sharing the same JVM can hold static state, singletons, threads, and process resources, making "least privilege" via a single interface insufficient.

If scripts are controlled by the development team and treated as trusted code, a **small API facade** is good design. If scripts or plugins come from untrusted parties, you need an **out-of-process execution path** or a sandbox environment with real protection guarantees and OS/network policies.

### 5.3. Typical Post-Upgrade Failure Modes

| Symptom | Cause to check |
|---|---|
| JVM fails to start when upgrading to JDK 24 | Launch script/manifest/container still requests enabling Security Manager |
| `System.setSecurityManager(...)` throws `UnsupportedOperationException` | Legacy API is permanently disabled |
| `if (getSecurityManager() != null)` code stops running checks | Getter is always `null` |
| Calling `AccessController.checkPermission` always fails | Changed to a check no longer applicable in the runtime model |
| `doPrivileged` blocks still run normally | No Security Manager exists to alter permission evaluation; do not infer protection |
| Policy file still exists in the project but has no expected effect | Security Manager policy mechanism no longer executes |
| Plugin "isolated" by a class loader can still read files | Class loaders do not restrict OS privileges |
| Tests pass on Java 17 but fail on Java 24 | Migration tests did not cover launch flags, API behavior, and the threat model |

## 6. What Mechanisms Should Replace It?

**There is no direct 1:1 JDK API replacement for the entire Security Manager.** The right mechanism depends on the real reason the Security Manager was previously used.

| Legacy goal | Modern design approach | Caveats to remember |
|---|---|---|
| Checking who may view/edit data | Authentication + authorization at API/service/database | Must re-verify per actor/tenant and operation |
| Trusted plugins calling host functions | Minimal interface/capabilities, provider allowlists, auditing | Does not protect against malicious plugins in the same JVM |
| Running **untrusted** scripts or Java code | Isolated process/container/VM, OS permissions, and resource quotas | Containers must be properly hardened, not assumed invincible by default |
| Preventing arbitrary file access | Dedicated user/namespace, read-only or omitted mounts, filesystem permissions | Checking Java `Path` in UI alone is insufficient |
| Preventing connections to internal networks | Network namespaces, egress policies, firewalls, and proxies/gateways | Must also inspect DNS, redirects, and endpoint metadata |
| Limiting CPU/RAM/forks | cgroups / OS process limits / timeouts, process count caps | `Thread.interrupt()` does not reliably stop all malicious code |
| Restricting sensitive actions | Gateway accepting allowed operation IDs, schema validation, quotas | Do not expose endpoints that invoke arbitrary reflection/classes/methods |
| Monitoring actions instead of controlling privileges | Logging/observability, tracing, or controlled instrumentation | Observation does not turn itself into a sandbox mechanism |
| Protecting transport channels and secrets | TLS/mTLS, keystores, secrets management, and JCA | Unrelated to execution privileges of untrusted bytecode |

**Layering by trust level:**

1. **Trusted host code:** apply secure coding, least-privilege OS permissions, authz at business boundaries, dependency and supply-chain checks.
2. **Internally approved plugins:** use stable SPI, API facades/capabilities, version pinning, reviews, and upgrade processes; treat as code with process-level privileges unless isolated further.
3. **Scripts or partner plugins not fully trusted:** route privileged operations through a gateway, restrict engine host access, and consider running out-of-process.
4. **Untrusted user code:** run in a dedicated worker process/container/VM with an unprivileged uid, restricted filesystem/network/secrets, timeouts, and quotas. Never use a class loader or a "fake SecurityManager" as the sole boundary.

## 7. Java 17 Example Replacing Checks with Explicit Business Authorization

In legacy apps, some authors might assume `SecurityManager` would stop a script from reading another user's report. However, **business authorization** should be enforced in the service/gateway itself rather than relying on global Security Manager state.

The following example clarifies only the **access contract**. It does not execute scripts and makes no claim of sandboxing malicious code; untrusted callers must still connect across a protected process/gateway boundary.

Save as **`CapabilityBoundaryDemo.java`**:

```java
import java.util.Set;

public final class CapabilityBoundaryDemo {

    enum Operation {
        READ_REPORT,
        EXPORT_REPORT
    }

    record AccessContext(String tenant, Set<Operation> grants) {}

    record ReportRecord(String tenant, String content) {}

    static String readReport(
            AccessContext context, ReportRecord report) {

        if (!context.grants().contains(Operation.READ_REPORT)
                || !context.tenant().equals(report.tenant())) {
            throw new SecurityException("DENIED");
        }
        return report.content();
    }

    public static void main(String[] args) {
        AccessContext context = new AccessContext(
                "team-a", Set.of(Operation.READ_REPORT));

        System.out.println("own=" + readReport(
                context, new ReportRecord("team-a", "report-1")));

        try {
            readReport(
                    context, new ReportRecord("team-b", "private"));
        } catch (SecurityException exception) {
            System.out.println("other=" + exception.getMessage());
        }

        System.out.println("exportGranted="
                + context.grants().contains(
                        Operation.EXPORT_REPORT));
    }
}
```

Compile and run with Java 17+:

```bash
javac --release 17 CapabilityBoundaryDemo.java
java CapabilityBoundaryDemo
```

Verified stdout:

```text
own=report-1
other=DENIED
exportGranted=false
```

**Explanation:**

- The host grants `READ_REPORT` to tenant `team-a`, so only records belonging to that tenant can be read.
- Reading `team-b`'s report is denied with `DENIED`.
- Without the `EXPORT_REPORT` grant, export permission is not granted.
- There are no calls to `SecurityManager`, `AccessController`, or policy files; the check lives directly inside the business operation.

**Do not misunderstand the protection model:** This example restricts actions **for callers that must go through `readReport`**. If untrusted code runs **inside the same JVM**, it may still find another path to data or APIs depending on environment accessibility. Therefore, in real products, `AccessContext` must be constructed by the host from an authenticated identity and **never** self-created by a script and trusted; read operations must pass through a gateway/repository that enforces ACLs, and untrusted code additionally requires process/OS isolation.

To be production-grade, use real authn/authz, enforce tenant scoping in data queries, audit decisions, limit sizes/queries, prevent bypasses, and test negative cases. An `AccessContext` record in demo code is just an easy-to-read representation, not an authentication mechanism.

## 8. Reference Architecture When Running Untrusted Plugins or Scripts

An architecture can separate **code execution** from **host privilege access**:

```text
Client / tenant
      |
      v
Host API: authn + authz + quota
      |
      +--> Create execution request (script, inputs, run ID)
                    |
                    v
          Sandbox worker process
           - unprivileged uid
           - no mounted secrets/host FS
           - network egress closed by default
           - cgroups/CPU/RAM/process limits
           - deadline + kill process on timeout
                    |
                    | IPC (fixed schema, auth context)
                    v
          Host capability gateway
           - operation allowlist
           - host-authenticated tenant/actor
           - input validation
           - per-call authorization
           - rate limits and auditing
                    |
                    v
          Java services / database
                    |
                    v
              Filtered DTO data
```

In this model:

- **The script worker holds no host database permissions or secrets.** When it needs an authorized action, it sends a narrow operation: `report.read`, `report.list`, or `event.emit`.
- **The gateway accepts no arbitrary class/method names.** Never expose `evalJava`, `invoke(String className, String method)`, `openFile(String path)`, or arbitrary URLs unless required by business rules.
- **Actor/tenant is determined on the host.** Never trust a self-supplied `tenantId` field inside a script payload.
- **Process boundaries** allow configuring uid, syscall/OS policies, mounts, network namespaces, RAM/CPU limits, and killing the worker on timeout without killing the host JVM.
- **Results are returned as size-bounded DTOs/JSON**, avoiding returning Java objects holding `ClassLoader`, `Connection`, `Path`, `DataSource`, or broader access privileges.
- **Terminating a process does not roll back committed side effects.** Write operations need idempotency keys, transaction boundaries, timeout reconciliation, and retry policies.
- **Containers are only one layer:** privileged mode, host filesystem mounts, service account tokens, or open networking can still grant the worker excessive privileges.

### 8.1. Avoid Misusing `SecurityException`

Java applications can still **throw `SecurityException` themselves** as in the `DENIED` example to signal a business error; the fact that the exception class still exists **does not mean the Security Manager is still active**. In real API systems, it is usually better to return specific application error codes such as `PERMISSION_DENIED` or `TENANT_SCOPE_VIOLATION`, without relying on `java.security.Policy` to determine grants.

## 9. Migration Plan from Security Manager on JDK 17–23 to JDK 24+

A migration must inspect **runtime configuration, Java sources, dependencies, tests, and security goals**.

### Step 1. Inventory Dependencies and Assumptions

Search source code and configurations for:

- `System.setSecurityManager(...)`, `System.getSecurityManager()`, `new SecurityManager()`, custom `SecurityManager` subclasses.
- `AccessController.checkPermission(...)`, `AccessController.doPrivileged(...)`, `Policy.setPolicy(...)`, `Policy.getPolicy()`, `AccessControlContext`, `ProtectionDomain.getPermissions()`.
- Configurations like `-Djava.security.manager`, `-Djava.security.policy`, `java.policy`, startup flags in container images, scripts, service managers, and build/test runners.
- Libraries using Security Manager to block `System.exit`, restrict files/network, sandbox plugins, or run user code.
- Libraries that only check `getSecurityManager()!=null` to decide whether to run checks; this group can **silently skip checks** on JDK 24.
- RMI remote class downloading or plugin frameworks whose design paths previously depended on Security Manager.

Identify the **reason** behind each Security Manager usage: protecting data, limiting I/O, blocking exit, logging API usage, or merely legacy library compatibility. Not all of them can be replaced with a single solution.

### Step 2. Use Tools and Transitional Testing

On a JDK with a compatible `jdeprscan`, you can scan classes/JARs for references to APIs deprecated for removal:

```bash
jdeprscan --release 17 --for-removal app.jar
```

`jdeprscan` is a **bytecode API scanning tool**; it does not guarantee finding reflection paths, config flags, dynamically downloaded JARs, or scripts calling APIs dynamically. Supplement it with code search and dependency inventories. On JDK 17–23, you can run the application with `-Djava.security.manager=disallow` to find code attempting to install a manager dynamically; this is a **transitional migration test**, not a way to restore Security Manager in JDK 24.

Also check **how the service actually starts**: Docker entrypoints, systemd, test JVM args, framework flags, and CI pipelines. If Java 24 fails to start due to `-Djava.security.manager=allow`, fix the configuration instead of suppressing the error.

### Step 3. Classify and Replace by Purpose

- **Application authorization:** move checks into services/repositories/gateways by actor, resource, action, and tenant.
- **Sandboxing third-party code:** move workloads into worker processes/containers/VMs with OS resource policies and minimal IPC.
- **Plugin lifecycle:** continue using `ClassLoader`/`ModuleLayer` to manage versions/code loading, while clearly separating them from security boundaries.
- **API interception:** evaluate static analysis, instrumentation, or wrapper design in place of SecurityManager hooks; interception tools do not by themselves guarantee a sandbox.
- **Legacy `doPrivileged`:** review why elevated privilege was requested; on JDK 24 actions execute normally with no Security Manager privilege-escalation model to rely on.
- **Testing assumptions:** update tests that previously expected `SecurityException` from platform libraries when blocked by Security Manager; behavior may now differ.

### Step 4. Deploy Safely Before Removing Legacy Code

1. Design a **threat model**: who supplies code/scripts, what data needs protection, and which actions must be blocked.
2. Establish the new boundaries **before** removing old Security Manager checks. Avoid stripping checks first only to discover untrusted plugins now hold broad privileges.
3. Write tests for denied scenarios: reading host files, reading secrets, connecting to internal networks, spawning processes, calling unauthorized operations, and exceeding quotas.
4. Test on JDK 24 with cleaned startup flags; measure successes, API errors, dependency warnings, and actual worker sandbox behavior.
5. Record audits/logs, distinguish app permission errors from OS errors, and limit exposure of sensitive info.
6. Promote to production only once legacy policies have equivalent or stronger replacements aligned with the threat model.

## 10. Recommended Test Matrix

| Test | Expectation |
|---|---|
| JDK 17 compiling legacy code with `SecurityManager` | Emits deprecation-for-removal warnings per compiler/options |
| JDK 24 calling `System.getSecurityManager()` | Always `null` |
| JDK 24 calling `System.setSecurityManager(null)` | Throws `UnsupportedOperationException` |
| JDK 24 using `-Djava.security.manager=allow` | JVM initialization error; application does not start |
| JDK 24 calling `AccessController.doPrivileged` | Action executes; creates no permission sandbox |
| JDK 24 calling `AccessController.checkPermission` | Throws `AccessControlException`; not usable as new authz |
| Application checking `getSecurityManager()!=null` to block files | Check branch does not execute; replacement control required |
| Plugin loaded by separate loader trying to read host file | Separate loader is not an OS boundary; test process sandbox |
| Script calling gateway to read another tenant | Gateway denies and returns no data |
| Untrusted worker attempting internal network calls | Egress policy blocks at OS/network level |
| Worker exceeding CPU/time/memory budget | Host throttles/kills worker without hanging main JVM |
| Worker killed after a write command | Idempotency/reconciliation policy prevents duplicate side effects |
| Scanning application with `jdeprscan` | Detects deprecated references within scanned bytecode |
| Packaging custom JDK runtime image | Security model still does not rely on Security Manager |

Test on the exact OS, container runtime, and JDK used in production, because a container with misconfigured mounts or network policies cannot be fixed by Java code calling `SecurityManager`.

## 11. Common Mistakes

1. **"Deprecated in JDK 17 means already removed."** False: JDK 17 marked it for future removal; JDK 24 permanently disabled it.
2. **"Disabled in JDK 24 means the API was deleted."** False: the API still exists in JDK 24 with altered behavior; removal is planned later.
3. **"Adding `-Djava.security.manager=allow` re-enables the manager."** False on JDK 24; the JVM refuses to start.
4. **"`System.setSecurityManager(null)` only clears the manager, so it must be safe."** False on JDK 24: it still throws `UnsupportedOperationException`.
5. **"`System.getSecurityManager()==null` means all permissions are denied."** False: it only reports that no Security Manager is active.
6. **"`AccessController.doPrivileged` grants a separate privilege level."** False on JDK 24: the action runs as when no Security Manager exists.
7. **"Calling `checkPermission` manually suffices to emulate legacy policies."** False: many methods now throw unconditionally rather than enforcing legacy permission policies.
8. **"`URLClassLoader` or `ModuleLayer` is a reliable sandbox."** False: those are class/module structural tools, not process/network/OS restrictions.
9. **"`ScriptEngine`/`JShell`/`JavaCompiler` restrict user permissions automatically."** False: they serve evaluation/compilation/execution under their own mechanisms and require trust boundaries.
10. **"A small Java interface guarantees a malicious script cannot call anything else."** False if the engine permits host interop or code shares the same JVM.
11. **"`SecurityException` still being thrown means Security Manager is active."** False: applications or other JDK APIs can throw this exception for their own reasons.
12. **"Containers provide complete isolation by default."** False: privileged mode, mounts, open networks, and high-privilege identities can defeat the boundary.
13. **"Scanning bytecode once is enough."** False: you must check launch flags, reflection, configs, scripts, runtime-added plugins, and dependencies.
14. **"Replacing Security Manager just means switching to an auth framework."** Auth frameworks govern request/data permissions; they do **not** isolate malicious code running with host process privileges.
15. **"Just deleting deprecated APIs makes it safe."** Before removing them, restore or design security invariants and test negative cases at the exact boundaries.

## 12. Checklist for Java 24+ Applications with Dynamic Code Loading

- No longer attempting to install/enable `SecurityManager` via APIs or JVM flags.
- No longer using `getSecurityManager()` as the sole condition to decide whether to check permissions.
- Not relying on `java.policy`, `Policy`, `AccessController.checkPermission`, or `doPrivileged` as new protection mechanisms.
- Inventoried dependencies, plugins, scripts, and dynamic compilation/class-loading paths.
- Classified code into **trusted**, **conditionally trusted**, and **untrusted**.
- Implemented capability/authorization at services/gateways with host-authenticated actor/tenant/grants.
- Protected data using appropriate OS permissions, secrets management, database ACLs, and network policies.
- If running untrusted code: dedicated workers with uid/FS/network isolation, CPU/RAM/deadline/process limits, and anti-bypass IPC.
- Disabled endpoints accepting arbitrary classes/methods/commands where not required by business logic; bounded inputs/outputs/side effects.
- Tested privilege-escalation attempts, timeouts, resource exhaustion, tenant spoofing, failure retries, and actual JDK upgrades.
- Clearly documented which security boundaries belong to the Java application and which are enforced by the OS/container/hypervisor.
- Removed tests that merely assumed "Security Manager is still enabled" and replaced them with tests for genuinely enforced policies.

### Original References

- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- [Security Manager Is Permanently Disabled — Java SE 24 Security Developer's Guide](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html)
- [SecurityManager API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html)

**Conclusion:** **JDK 17** marks the Security Manager as **slated for removal**; **JDK 24** **permanently disables** this mechanism, though the API remains present to support transition. Any Java system capable of loading plugins or scripts cannot rely on `SecurityManager` to isolate foreign code. You must transition to **explicit business authorization**, **authenticated capabilities/gateways**, and **process/OS isolation** when executing untrusted code.
