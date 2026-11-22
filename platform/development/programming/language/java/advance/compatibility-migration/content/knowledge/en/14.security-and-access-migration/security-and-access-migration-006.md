# Security Manager: Support Status by Version and Replacement Approaches

In Java Advance Compatibility Migration, many legacy applications use `SecurityManager` to restrict file operations, networking, loading native libraries, reading system properties, or calling `System.exit`. Some application servers, plugin systems, testing tools, and Java libraries also have code calling `System.setSecurityManager(...)`, `AccessController.doPrivileged(...)`, or reading `java.policy` files. Mechanisms that worked on JDK 8 or JDK 11 may emit warnings on JDK 17–23 and no longer work when moving to JDK 24 or later.

**Most importantly:** Security Manager **has no new 1:1 equivalent Java SE replacement API**. Java has shifted away from fine-grained per-code permission sandboxing inside the same JVM. Therefore, you must identify which resources the Security Manager was protecting, which code is considered trusted, and where the threat boundaries lie, then move the appropriate controls to **the OS/process, container/VM, file and network permissions, application authentication/authorization mechanisms, IAM, and dependency governance**.

This lesson covers the status by JDK release, how to identify dependencies still relying on the Security Manager, API/option changes, migration examples, and a safe rollout plan. The focus of the **Security and Access** chapter is avoiding accidentally dropping protective boundaries when upgrading Java.

## 1. What Was Security Manager Used For?

`java.lang.SecurityManager` is a legacy mechanism for checking permissions before certain Java APIs perform sensitive operations. When a Security Manager is enabled, the JDK or application can call methods such as `checkRead`, `checkWrite`, `checkConnect`, and `checkPermission` to allow or deny operations based on policy and context.

Example of permission checking in a legacy application:

~~~java
SecurityManager manager = System.getSecurityManager();
if (manager != null) {
    manager.checkRead("/srv/app/config.yml");
}
~~~

Under the legacy model, an application could use:
- `java.security.Permission` and types such as `FilePermission`, `SocketPermission`, and `RuntimePermission`.
- `java.security.Policy` and policy files granting permissions by code source, signer, or protection domain.
- `AccessController.checkPermission` and `AccessController.doPrivileged`.
- System property `java.security.manager` to enable or allow installing a Security Manager.
- System property `java.security.policy` or `java.policy` files to specify policies.

However, this model has architectural limitations: code within the same process/JVM shares many resources, new APIs must integrate corresponding checks, and JNI/native code alongside other runtime mechanisms make building a trustworthy sandbox very difficult. Security Manager is also not a control layer for every type of resource access. Thus, an application running with Security Manager is **not automatically a strong enough sandbox for untrusted code**.

### 1.1. Do Not Confuse Security Manager with Other Security Mechanisms

The following concepts are independent of Security Manager:

| Concept | Purpose | Depends on Security Manager? |
|---|---|---|
| Java Cryptography Architecture (JCA/JCE) | Encryption, signatures, hashes, providers, keys | Does not require Security Manager for standard crypto functionality |
| TLS/JSSE | Protecting network connections | Not a Security Manager mode |
| JAAS, Subject, principal | Identity and security context in related APIs | Some legacy Security Manager-interacting APIs changed; check version |
| Application authorization | Checking who may read/modify business data | Enforced by the application/service; cannot be delegated entirely to Security Manager |
| JPMS | Modularization and strong encapsulation | Not a sandbox for untrusted code |
| Container/OS isolation | Resource limits and process privileges | Independent of Security Manager |
| Dependency integrity | Artifact selection, signatures, checksums, supply chain | Requires separate build/deployment management mechanisms |

Removing Security Manager **does not mean removing all Java security**. It means legacy policy-based permission checks of Security Manager can no longer be relied upon in modern JDKs.

## 2. Security Manager Status by JDK Version

The status changes across phases, so do not write a single rule covering JDK 8, 17, and 24.

| JDK | Support status | Impact on migration |
|---|---|---|
| JDK 8 | Security Manager exists and can be enabled | Applications may rely on `java.policy`, custom SecurityManager, `doPrivileged` |
| JDK 9–16 | Still exists; some platform/JPMS mechanisms changed the approach | Need to re-test policies, module access, and libraries |
| JDK 17 | **Deprecated for removal** per JEP 411 | Compiler/API warnings; enabling or installing a manager emits runtime warnings |
| JDK 18–23 | Still has a conditional support phase; dynamic installation is restricted by default | Do not rely on `setSecurityManager` succeeding without the appropriate launch option |
| **JDK 24 and later** | **Permanently disabled** per JEP 486 | Cannot be enabled at startup or installed at runtime; many related APIs still exist with changed semantics or throw exceptions |

Java update releases or JDK vendors may differ in tooling, packaging, or non-specification features. When surveying a system, explicitly record the **vendor, major version, update/build, and actual runtime JVM**. Do not draw conclusions from the Java version on the build machine.

### 2.1. JEP 411 in JDK 17: Warnings and Preparation for Removal

JEP 411 marks Security Manager and related APIs as **deprecated for removal** starting in JDK 17. This means removal is planned for the future, **not that JDK 17 deleted the `SecurityManager` class**.

During the JDK 17–23 period, applications can still use Security Manager under runtime-supported conditions, but should:
- Identify use cases relying on policy-based permission checks.
- Locate all call sites of `System.setSecurityManager`, `Policy.setPolicy`, or permission checks.
- Monitor compile/runtime warnings.
- Review runbooks and startup options.
- Plan to eliminate the dependency before moving to JDK 24+.

In JDK 17–23, you can use `-Djava.security.manager=disallow` to **test the application when installing a Security Manager is disallowed**. When code tries to install a manager via `System.setSecurityManager`, testing can surface `UnsupportedOperationException`. This is a migration preparation test, not a solution for applications needing a real sandbox.

### 2.2. Dynamic Installation and Defaults Differ Across JDKs

Some legacy code calls:

~~~java
System.setSecurityManager(new SecurityManager());
~~~

Previously, behavior depended on current state and how the JVM was launched. In JDK 18–23, if dynamic installation is not allowed by the launch configuration, installation may be rejected. Values of `java.security.manager` such as `allow`, `disallow`, and `default` play different roles depending on the release.

**Do not carry JDK 17/21 launch flags verbatim into JDK 24.** On JDK 24+, attempting to enable or allow Security Manager at startup causes a JVM initialization failure. There is no new flag to “re-enable” the disabled Security Manager mechanism.

### 2.3. JEP 486 in JDK 24+: Permanently Disabled

Starting in JDK 24, Security Manager is **permanently disabled**:
- Launching the JVM with `-Djava.security.manager` to enable or allow a manager (such as `allow`, `default`, or a custom class name) results in a startup failure.
- Calling `System.setSecurityManager(SecurityManager)` throws `UnsupportedOperationException`.
- `System.getSecurityManager()` always returns `null`.
- `AccessController.doPrivileged(...)` executes the action as when no Security Manager is present, without granting special privileges under the old mechanism.
- Strict permission-checking methods such as `AccessController.checkPermission` and `SecurityManager.check*` always deny/throw according to the adjusted API.
- `Policy.setPolicy(...)` throws `UnsupportedOperationException`; policy file mechanisms for Security Manager no longer carry their previous enforcement semantics.
- The system policy file `$JAVA_HOME/conf/security/java.policy` is no longer part of the JDK configuration mechanism as before.

**Distinguish “disabled” from “API removed”.** In JDK 24/25, many deprecated class/method names may still exist to preserve linkage for legacy libraries, yet no longer provide the former Security Manager functionality. These APIs remain slated for removal in a future JDK release. Code compiling because class names still exist **does not prove the old policy still works**.

### 2.4. Impact on Classpath/Module Path and Startup

Example of a legacy script:

~~~bash
java \
  -Djava.security.manager \
  -Djava.security.policy=/opt/app/security/app.policy \
  -jar legacy-app.jar
~~~

For JDK 24+, this command cannot be kept as a way to activate policies. You must determine the purpose of `app.policy`, replace it with another permission boundary, and remove the flag enabling Security Manager.

Simply deleting the flag so the JVM starts is **not completing the security migration**. When the previous policy forbade reading files or making outbound connections, dropping that mechanism can leave the process with broader permissions. Replace the controls before or alongside changing the runtime.

## 3. APIs and Behaviors Requiring Individual Verification

Because many libraries still call Security Manager APIs, understanding exact behavior from JDK 24 onward helps distinguish “temporarily running” code from code whose contract is broken.

| API or mechanism | Behavior to note from JDK 24 | Handling approach |
|---|---|---|
| `System.getSecurityManager()` | Always returns `null` | Remove Security Manager check branches; do not infer “sandboxed” from null |
| `System.setSecurityManager(...)` | Always throws `UnsupportedOperationException` | Remove manager installation logic and replace the control mechanism |
| `AccessController.doPrivileged(...)` | Runs the action directly under no-manager semantics | May still exist in libraries, but no longer carries legacy privilege-granting meaning |
| `AccessController.checkPermission(...)` | Throws `AccessControlException` | Replace with an application-level authorization model if used for permission checks |
| `SecurityManager.checkPermission/check*` | Checks on manager instances can no longer enforce legacy policies | Remove custom checkers and move enforcement to the appropriate layer |
| `Policy.setPolicy(...)` | Throws `UnsupportedOperationException` | Do not rely on Java policy files to create a sandbox |
| `java.security.policy`, `java.policy` | No longer controls Security Manager | Move resource controls to OS/container/app |
| Policy-related `Permission/ProtectionDomain` | Some methods return empty/null/false under new semantics | Do not use them as an authorization decision source |

Avoid overgeneralizing that “all Security Manager APIs are no-ops”. **Some methods do nothing, some return null/false, and some unconditionally throw exceptions.** The migration process must be based on the specific API and target JDK.

### 3.1. The “If Security Manager Is Present, Check Permission” Idiom

Example in a legacy library:

~~~java
SecurityManager manager = System.getSecurityManager();
if (manager != null) {
    manager.checkPermission(new RuntimePermission("createClassLoader"));
}
~~~

On JDK 24+, `getSecurityManager()` always returns `null`, so the check branch never runs. If the library only used this snippet to cooperate with an optional Security Manager mechanism, it can continue operating. However, if the application relied on this check as its **primary security barrier**, that barrier has disappeared.

Do not “fix” this by directly instantiating a SecurityManager and calling `checkPermission` to force checks: the semantics of these methods have changed and they are no longer a supported authorization framework.

### 3.2. The doPrivileged Idiom

Legacy code:

~~~java
String value = java.security.AccessController.doPrivileged(
        (java.security.PrivilegedAction<String>)
        () -> System.getProperty("app.mode")
);
~~~

In earlier environments with a Security Manager, `doPrivileged` interacted with the permission-check stack. On JDK 24+, the action executes like a normal call.

If it only needs to read a system property for application functionality, it can be simplified to:

~~~java
String value = System.getProperty("app.mode");
~~~

However, before removing the wrapper across many places, check whether any checked exceptions, other overloads, or context propagation are used by the library. Cleaning up deprecated APIs should be done deliberately and tested for behavioral changes.

### 3.3. Custom Permission Checkers Are a Separate Issue

Some frameworks use `AccessController.checkPermission` as part of a custom-built authorization engine. On JDK 24+, it does not become an application-level permission-checking function; this method throws an exception under the new semantics.

If the application wants to check “does user A have permission to export reports?” or “may plugin P access secret Q?”, the system must have its own policy/authorization:
- Identity of the caller/service/plugin.
- Specific resource and action.
- Data-backed and versioned permission rules.
- Decision auditing and deny-by-default enforcement.
- Policy enforcement points that cannot be bypassed via another API.

Do not adopt `java.security.Permission` classes as a new default authorization framework merely because the name contains the word Security.

## 4. Inventorying Dependencies Before Upgrading the JDK

Security Manager can be activated by the main entrypoint, an application server launcher, a test framework, a build plugin, an agent, or a transitive library. Searching only for `new SecurityManager()` in main source code is not enough.

### 4.1. Searching in Source Code and Configuration

With ripgrep:

~~~bash
rg -n --hidden \
  -g '!**/.git/**' -g '!**/build/**' -g '!**/target/**' \
  'SecurityManager|setSecurityManager|getSecurityManager|AccessController|AccessControlContext|Policy\.setPolicy|checkPermission' .

rg -n --hidden \
  -g '!**/.git/**' \
  'java\.security\.manager|java\.security\.policy|\.policy|doPrivileged|checkRead|checkWrite|checkConnect' .
~~~

When encountering `.policy`, distinguish Java Security Manager policies from policies belonging to other systems. Do not delete files solely because of a matching extension.

Do not forget:
- Gradle/Maven plugins, test runners, and agents.
- Startup scripts, systemd units, Windows services, Dockerfiles, and Helm charts.
- CI variables such as JAVA_TOOL_OPTIONS or JDK_JAVA_OPTIONS.
- Application server configurations, policy files, or VM options outside the repository.
- Third-party JARs using reflection/dynamic class loading.
- Consumers/plugins loaded at runtime that are absent from build-time sources.

### 4.2. Finding Deprecated APIs in Artifacts

With a JDK supporting `jdeprscan`, you can scan built JARs:

~~~bash
jdeprscan --release 17 app.jar
~~~

Choose a `--release` supported by the current tool and matching the baseline under review. `jdeprscan` reports deprecated Java SE APIs statically referenced in class files; it does not prove whether code actually enables Security Manager or find reflection-based calls.

On JDK 17–23, the Java launcher typically emits warnings when Security Manager is enabled/installed via deprecated mechanisms. Record these warnings as evidence, but **do not rely solely on warnings**: a library may have code paths that only run when a feature flag/plugin is enabled.

### 4.3. Using JDK 17–23 to Detect Dynamic Security Manager Installation

On a JDK in the 17–23 range that supports this test setting, you can run the application:

~~~bash
java \
  -Djava.security.manager=disallow \
  -jar app.jar
~~~

If startup or a functional flow attempts `System.setSecurityManager`, `UnsupportedOperationException` may be caught. Exercise all critical business flows, plugins, tests, and jobs, not just the health check.

**Do not use this command on JDK 24+ as an equivalent test.** Security Manager is permanently disabled; the semantics of launch options and APIs are no longer the same as in earlier versions.

### 4.4. Building a Dependency Inventory

A useful inventory template:

| Field | Example |
|---|---|
| Source/artifact | `legacy-plugin-engine:2.3` |
| Caller | `PluginLoader.installSandbox` |
| API | `System.setSecurityManager` |
| Previous goal | Prevent plugins from reading system files |
| Baseline JDK | JDK 11 |
| Target JDK | JDK 25 |
| Behavior if removed | Plugins running in-process can access files per the service's OS permissions |
| Risk | Loss of protective boundary between plugins and secrets |
| Replacement | Run plugins in a separate process/container with minimal file/network privileges |
| Owner | Platform team |
| Verification | Verify plugins cannot read unmounted/ungranted secrets |
| Status | Pending / Migrate / Verified |

Be careful to distinguish **hard dependencies** on Security Manager from **conditional compatibility code**. A library that only checks `getSecurityManager() == null` may run fine; a library building a custom policy engine with `AccessController.checkPermission` will require deeper changes.

## 5. Threat Model: What Did Security Manager Protect?

To replace it properly, first identify the assets needing protection and the kind of code being constrained.

| Scenario | Risk to constrain | Where to place replacement controls |
|---|---|---|
| Service reads/writes files | Exposing secrets or modifying system files | User/process permissions, filesystem ACLs, read-only mounts, minimal secret provisioning |
| Service makes network connections | Unauthorized database access or data exfiltration | Network policies, egress firewall/proxy, identity, and TLS |
| Partner-provided plugins | Untrusted code running inside the JVM and touching process resources | Separate process/container/VM; authenticated/authorized communication APIs |
| Multi-tenant application | One tenant's data being read by another tenant | Tenant isolation at the data/service layer, query authorization, and auditing; separate processes when needed |
| Running user-submitted scripts/expressions | Arbitrary code execution or resource exhaustion | Dedicated hardened sandbox process, quotas, timeouts, syscall/network controls |
| Using System.exit | Secondary code shutting down the process | Lifecycle management, process isolation, plugin API design; agent interception is not a security sandbox |
| Test framework using SecurityManager to block exit | Tests terminating when code calls System.exit | Run tests in a subprocess/fork and assert exit code and output |
| RMI remote code download | Code downloaded from elsewhere and executed in the JVM | Remove unnecessary remote loading mechanisms, control artifact distribution, and enforce trusted deployment |

**A single replacement mechanism rarely addresses every row in the table.** For example, a NetworkPolicy restricts networking but does not control code reading a secret file already mounted inside the container. Role-based authorization protects business APIs, yet does not stop native code from reading a file permitted by the process's OS permissions.

### 5.1. Protecting Against Untrusted Code Is the Hardest Use Case

If the legacy model ran untrusted plugins/scripts in the same JVM hoping Security Manager would prohibit dangerous operations, you must change the execution boundary. Code in the same process can often observe or affect many process-shared resources. A `ClassLoader` or JPMS module is **not** a substitute security boundary.

A more robust design:

~~~text
                     Trusted application
                             |
             Validated request + capabilities
                             |
                    Authenticated IPC
                             |
                    Plugin worker process
                    /        |         \
             restricted   resource     timeout
               files      quotas       policy
                    \        |         /
                       OS/container
                         isolation
                             |
                   Minimal external access
~~~

The worker receives **only the inputs/capabilities genuinely required**, runs under a separate service account or inside a hardened sandbox runtime, and communicates over a versioned, authorized protocol. Do not expose database root credentials or the main application's secret directories to the worker unless necessary.

Containers aid isolation, yet **do not automatically guarantee a secure sandbox under default settings**. Evaluate kernel isolation, root/capabilities privileges, mounts, seccomp, AppArmor/SELinux, networking, namespaces, cgroup limits, image integrity, and upgrade policies. For very low trust or highly sensitive data, a VM/microVM or dedicated isolated infrastructure may be more appropriate.

## 6. Replacing by Control Layer

### 6.1. Filesystem: Process Permissions Instead of FilePermission

A legacy Java policy might restrict a plugin to reading only a specific directory. When moving to OS controls:
- Run the service/worker under a dedicated user with least privilege.
- Use appropriate file ownership/permissions/ACLs.
- Mount only the necessary directories, read-only wherever possible.
- Do not mount the host Docker socket, home directories, or secret stores into untrusted workers.
- Apply OS/container restrictions such as a read-only root filesystem when the workload allows.
- Enable audit logging when unusual operations need to be tracked.

Principle example: if a worker only needs to read `/data/input` and write `/data/output`, do not grant access to `/srv/app` or credential directories. Java code continues using `Files.readString` normally; access control is enforced at the OS/filesystem layer.

### 6.2. Network: Egress Policies and Identity

A `SocketPermission` previously restricted host/port access. Replacement approaches:
- NetworkPolicy or firewall/egress gateway for the process/container.
- Appropriate DNS and routing policies; avoid relying solely on string hostname checks.
- Service identity, mutual TLS, or narrowly scoped tokens for permitted connections.
- Network segmentation so workers cannot directly call metadata services, the control plane, or unrelated databases.
- Logging and alerts for violating egress behavior.

Network policies do not replace authentication/authorization. If a worker is permitted to call an API, that API must still verify the permissions of the worker identity and each requested resource.

### 6.3. Process and Resource Controls

In an OS/container environment, you can use:
- Dedicated users/groups, namespaces, and privilege-dropping mechanisms.
- CPU/memory/PID quotas, timeouts, and watchdogs.
- Seccomp or equivalent sandboxes to restrict syscalls appropriately.
- Filesystem mount namespaces, read-only mounts, and volume permissions.
- Isolated processes to contain `System.exit`, JVM crashes, or unbounded memory allocation.
- A process supervisor capable of restarting/reaping workers and recording telemetry.

No single option fits every OS. The design must match the threat model, deployment environment, and type of code being handled. Compatibility between OS security policies and native/JNI applications must also be verified.

### 6.4. Authorization Inside the Application

If Security Manager was used to check “is this user allowed to export an invoice?”, move that check to a dedicated authorization service/layer instead of checking `RuntimePermission`.

Example domain-level interface:

~~~java
public interface AuthorizationService {
    boolean canReadInvoice(String principalId, String invoiceId);
}
~~~

Usage:

~~~java
public final class InvoiceService {
    private final AuthorizationService authorization;

    public InvoiceService(AuthorizationService authorization) {
        this.authorization = authorization;
    }

    public String readInvoice(String principalId, String invoiceId) {
        if (!authorization.canReadInvoice(principalId, invoiceId)) {
            throw new SecurityException("Invoice access denied");
        }
        return loadInvoiceFromDatabase(invoiceId);
    }

    private String loadInvoiceFromDatabase(String invoiceId) {
        // Illustration: query through a repository with tenant/resource scoping.
        return "invoice:" + invoiceId;
    }
}
~~~

This is an example of where to check permissions, **not a complete authorization implementation**. In a real product, identity must be authenticated rather than trusting an arbitrary client-supplied `principalId`; database queries and repositories must enforce tenant/resource scoping along with auditing/deny-by-default. Checking first and then executing the operation through a different unchecked API can introduce bypasses or TOCTOU issues.

### 6.5. IAM and Secret Management

If legacy code used Security Manager to stop plugins from reading environment variables or configurations containing secrets, the new model should rely on:
- Provisioning minimal secrets strictly to the right process.
- Service workload identities/roles, short-lived tokens, and narrow access scopes.
- Separating credentials between the main application and workers.
- A secret store/KMS with policies and auditing.
- Never writing secrets to logs, dumps, or command lines.
- Rotating and revoking credentials upon suspected exposure.

Once a secret has been mounted or loaded into a process's memory, trying to “forbid” a library in the same process from reading it using a pure Java API is not a reliable barrier against untrusted code.

## 7. Migration Example: Replacing Java Policy with Out-of-Process Isolation

Suppose a legacy plugin system has the policy:

~~~java
grant codeBase "file:/opt/app/plugins/*" {
    permission java.io.FilePermission "/srv/shared/public/-", "read";
    permission java.net.SocketPermission "api.partner.example:443", "connect,resolve";
};
~~~

This is an example of **legacy policy syntax**, not a valid configuration on JDK 24+. The original intent was to restrict plugins to reading one filesystem region and connecting to one network endpoint. If you merely delete `-Djava.security.manager`, the plugin may inherit the broad file/network privileges of the application process.

Migration direction:
1. Move plugins to a separate process/worker; do not run plugin code directly in the same JVM holding secrets.
2. Run the worker under a narrowly scoped user/identity.
3. Mount only the data that needs to be read; do not mount the main application directory.
4. Allow outbound traffic only to approved services via egress policies.
5. Target APIs authenticate the worker and enforce resource permissions by identity.
6. Communicate between the main application and worker over a well-defined protocol; validate inputs/outputs.
7. Configure timeouts, memory limits, and mechanisms to stop/restart the worker process.
8. Create security tests proving the plugin cannot access files/network outside its scope.

### 7.1. Tests Must Verify Denied Behavior

Do not test only that “the plugin processes valid tasks successfully”. Add cases to:
- Attempt to read an unmounted/ungranted secret file.
- Attempt to write to a read-only directory.
- Attempt to open a connection to a host outside the allowlist.
- Attempt to use the worker identity to access another tenant's resources.
- Attempt to push a task past CPU/memory/time quotas.
- Trigger a crash or call `System.exit` inside the worker: the main application should not die with it.
- Send malformed or oversized payloads to the IPC endpoint.

**Evidence to record** includes decisions from the OS/network/auth layers, exit status, and logs; not merely whether a Java method throws `SecurityException`. Security Manager is no longer the enforcement layer.

### 7.2. Preserving Legacy Functionality Without Keeping the Legacy Mechanism

If the actual goal is simply “allow the plugin to process input data and produce output”, you can design the plugin API to receive already-authorized data without giving the plugin direct file/network access. This reduces both required permissions and the attack surface.

However, a capability-oriented API only makes sense when capabilities cannot be bypassed via other access paths within the same security boundary. If an untrusted plugin still runs inside a process holding all secrets, passing a `RestrictedFileReader` object does not stop it from calling `Files.readAllBytes` with the process's OS permissions. Therefore, **API design and process isolation must go hand in hand** when defending against untrusted code.

## 8. Test Frameworks and the Need to Intercept System.exit

Some older test frameworks install a Security Manager to intercept `System.exit(1)` in code under test. On JDK 24+, that installation approach no longer works.

### 8.1. Replacing with Subprocess Testing

Instead of running code that might call exit directly inside the test runner's JVM, run it in a separate Java process:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

public class ExitCodeHarness {
    public static void main(String[] args) throws Exception {
        String javaBin = Path.of(
                System.getProperty("java.home"), "bin", "java"
        ).toString();

        Process process = new ProcessBuilder(
                javaBin,
                "-cp",
                System.getProperty("java.class.path"),
                "com.example.cli.Main"
        ).inheritIO().start();

        boolean finished = process.waitFor(
                Duration.ofSeconds(10).toMillis(),
                TimeUnit.MILLISECONDS
        );
        if (!finished) {
            process.destroyForcibly();
            throw new IllegalStateException("CLI exceeded timeout");
        }

        int exit = process.exitValue();
        if (exit != 0) {
            throw new AssertionError("Unexpected exit code: " + exit);
        }
    }
}
~~~

In the example, `com.example.cli.Main` is the application class under test. The child process has its own exit status and therefore does not terminate the test runner JVM. Real tests must manage stdout/stderr, output size, classpath/module path, environment variables, process tree cleanup, and timeouts. Do not use `inheritIO` if you need to capture output for assertions or worry logs may contain secrets.

### 8.2. Refactoring Code for Testability

When you can modify the application, separate business logic from the entrypoint:
- Business methods return results or throw appropriate exceptions.
- `main` maps the result to an exit code.
- Unit tests invoke the logic directly without installing a Security Manager.
- Integration tests launch a process to verify the exit code.

This reduces the need to intercept `System.exit`. A Java agent using bytecode instrumentation can help certain tests/frameworks, yet is **not a security sandbox** and does not replace a process boundary for untrusted code.

## 9. Compatibility of Libraries and Frameworks

Not every dependency referencing Security Manager causes an application to fail on JDK 24. Classify them:

**Group 1: uses manager optionally.**

~~~java
if (System.getSecurityManager() != null) {
    // permission checks when the manager is actually enabled
}
~~~

On JDK 24+, this branch never executes. If the application does not rely on that permission check to protect resources, the library can continue operating, though updating its version and dropping deprecated APIs is still recommended.

**Group 2: wraps actions in doPrivileged.**

~~~java
AccessController.doPrivileged(() -> {
    initializeCache();
    return null;
});
~~~

On JDK 24+, the action executes like a normal call. Code may run, but the wrapper should not be treated as evidence of a security boundary.

**Group 3: installs a custom manager or dynamic policy.**

~~~java
System.setSecurityManager(new MySecurityManager());
~~~

This is a clear blocker on JDK 24+ because the operation is no longer supported. Update the framework or change the architecture.

**Group 4: calls checkPermission as an authorization engine.**

~~~java
AccessController.checkPermission(
    new RuntimePermission("someOperation")
);
~~~

JDK 24+ behavior is not equivalent to the legacy policy engine; replace it with application authorization or an out-of-process boundary. Do not simply catch and ignore the exception, as that can turn a deny into an allow.

**Group 5: relies on legacy remote code download/RMI behavior.**

Certain RMI code loading capabilities previously relied on Security Manager; JDK 24 removes that default remote code downloading mechanism. Move to controlled artifact distribution/deployment rather than re-enabling dynamic code loading from untrusted sources. If the application truly requires remote plugins, redesign trust, verification, and process isolation.

## 10. Do Not Confuse Security Manager with Other JDK Controls

### 10.1. JPMS Does Not Replace Security Manager

JPMS manages:
- Module readability.
- Exported packages.
- Open packages for reflection.
- Dependency structure and encapsulation.

JPMS helps restrict undeclared **API access paths**, but it is not a sandbox for untrusted Java bytecode. `--add-opens`, `--add-exports`, and `--add-reads` are module-access options; they **do not re-enable Security Manager** and do not prevent a process from reading files or opening connections allowed by OS permissions.

### 10.2. Security Properties Differ from java.policy

Java still maintains security properties for JCA, providers, disabled algorithms, TLS, and many other features. Do not delete the entire `java.security` file or remove TLS configuration just because Security Manager is no longer supported.

Distinguish:
- Properties specifically for legacy `SecurityManager`/policy files.
- Security properties for JCA/JSSE, providers, and algorithms.
- Policies/roles of the application or external systems.

Some properties previously used for Security Manager become unsupported on JDK 24, while other Java security settings remain in effect. Read the specific release documentation before cleaning up startup flags.

### 10.3. Java Agents Do Not Replace an OS Sandbox

An agent can use `java.lang.instrument` to observe or transform bytecode during class loading. That suits observability, testing, or controlled instrumentation. However, an agent is not a trusted execution boundary for untrusted code in the same process: dynamic class loading, native code, method handles, uninstrumented call paths, and bypass risks still remain.

If the goal is restricting untrusted plugins from reading secrets or opening network connections, prioritize isolation at the OS/container/VM level and a least-privilege architecture.

## 11. Testing Across JDK Versions

### 11.1. Identifying the Actual Runtime

~~~bash
java -version
java -XshowSettings:properties -version
~~~

When the application runs in a container/service, check the Java of the **actual process**. Inspect the Docker ENTRYPOINT, Kubernetes command/args, startup scripts, service units, and environment injections. Do not infer from the JDK installed on a developer machine.

### 11.2. Illustrative Test Matrix

| Test | JDK 11 or baseline | JDK 17–23 | JDK 24+ |
|---|---|---|---|
| JVM startup without enabling Security Manager | Usually runs | Usually runs | Runs if not dependent on legacy mechanism |
| Installing manager via startup flag | May run under legacy policy | Conditional with warnings | **Unsupported; may fail immediately at startup** |
| Calling System.setSecurityManager | Depends on policy/config | Conditional; may throw UOE | **Always throws UOE** |
| Checking System.getSecurityManager() | May be null or non-null | May be null or non-null | **Always null** |
| AccessController.doPrivileged | Manager-related behavior if enabled | Depends on manager state | **Executes action directly** |
| Permission policy from java.policy | May serve as legacy control | Conditional | **Does not enforce legacy sandbox** |
| OS file/network permissions | Enforced by OS | Enforced by OS | Enforced by OS |
| App authentication/authorization | Per application implementation | Per application implementation | Per application implementation |

UOE here stands for `UnsupportedOperationException`. The matrix aids planning and **does not replace testing on the specific vendor/build**.

### 11.3. Deliberate Testing to Detect Remaining Dependencies

On JDK 17–23:
1. Run the application with critical features enabled.
2. Check Security Manager warnings.
3. Run a test pass with `-Djava.security.manager=disallow` to detect dynamic installation.
4. Run dependency scanners to find deprecated API references.
5. Record business flows that still rely on permission checks.

On JDK 24+:
1. **Do not use** flags enabling/allowing Security Manager.
2. Run startup, plugin loading, integration tests, and custom policy code paths.
3. Verify no `setSecurityManager` or `Policy.setPolicy` calls break startup/features.
4. Verify the replacement sandbox mechanism actually denies out-of-scope access.
5. Ensure OS/container IAM/permission configurations are deployed concurrently.

Save stack traces, JDK versions, artifact checksums, launch commands, and deny test results. Do not make tests “pass” by simply catching and ignoring `SecurityException` or `UnsupportedOperationException`.

## 12. Step-by-Step Migration Process

### Step 1: Inventory Security Manager Usage Sites

Search source code, configuration, dependencies, frameworks, tests, and policy files. Identify who installs the manager, who checks permissions, and which resources are protected.

### Step 2: Categorize by Role

At a minimum, divide into:
- Sandbox for untrusted code/plugins.
- Policies restricting files/network/processes.
- Business authorization.
- Tests intercepting `System.exit`.
- Libraries that only call `getSecurityManager/doPrivileged` when a manager is present.
- Libraries directly using `checkPermission` or dynamic policies.

Each group has a different replacement; do not create one generic wrapper replacing SecurityManager for every purpose.

### Step 3: Design New Permission Boundaries

If defense against untrusted code is needed, move to an appropriate process/container/VM. If only user authorization is needed, enforce authorization at the API/data layer. If only exit code testing is needed, use a subprocess. If a library uses deprecated APIs without needing a sandbox, upgrade the library and remove wrappers when safe.

### Step 4: Build “Deny” Tests Before Removing Legacy Policies

Create prohibited access cases: files, secrets, network, other tenants, process lifecycle, and resource exhaustion. Tests must measure the new boundary, not merely assert that a manager exists.

### Step 5: Update Build, Dependencies, and Launch Config

- Pin JDK and library versions with an appropriate support matrix.
- Remove `-Djava.security.manager` flags enabling/allowing the manager.
- Remove legacy Java policy settings from startup once replacement controls are in place.
- Do not delete unrelated security properties.
- Update container users, mounts, network policies, workload identities, and secrets.
- Update framework/plugin versions so they do not dynamically install a manager.

### Step 6: Test on the Target JDK

Run unit, integration, contract, and security tests. Check startup, plugin loading, data access, and permission violation scenarios. For high-risk plugins, test breaking the boundary with the actual granted permissions inside an isolated test environment; do not rely on the absence of a SecurityException.

### Step 7: Rollout and Operations

Deploy from staging/canary, monitoring denied accesses, startup errors, plugin failures, crashes, timeouts, audit events, network egress, and secret accesses. Have a clear rollback plan while avoiding blindly rolling back to a model that lost deployment-level isolation.

### Step 8: Eliminate Long-Term Dependencies

Once every use case has a replacement, remove deprecated APIs and unused policy files, and add regression checks to CI. Document in runbooks that Security Manager is not a supported security mechanism on JDK 24+.

## 13. Mistakes to Avoid

- **Assuming JDK 17 deleted the SecurityManager class:** JDK 17 only deprecated it for removal; JDK 24+ permanently disables it.
- **Assuming JDK 24 deleted all APIs from bytecode:** many methods still exist with changed semantics; they may be removed in the future.
- **Simply deleting launch flags so the application runs:** can strip file, network, or plugin restrictions that previously relied on the old policy.
- **Using --add-opens/--add-exports to “re-enable” the manager:** JPMS access options do not restore Security Manager.
- **Catching UnsupportedOperationException and continuing:** can turn a previous safety boundary into a no-op.
- **Treating AccessController.doPrivileged as a sandbox:** starting in JDK 24, it executes the action normally.
- **Treating AccessController.checkPermission as a still-supported authorization API:** Security Manager semantics have changed.
- **Searching only in application source code:** dependencies, agents, application servers, and test runners can install a manager.
- **Assuming default Docker is a complete sandbox:** hardening, least privilege, network restrictions, and host protection are required.
- **Using RBAC to replace file/network isolation:** RBAC protects business APIs but does not block process syscalls.
- **Testing only “allow” without testing “deny”:** does not prove the new policy actually restricts permissions.
- **Dropping security policies without documenting the threat model:** loses track of what functionality was previously protected.
- **Confusing java.policy with other Java security properties:** can accidentally weaken TLS/JCA settings.
- **Treating ClassLoader/JPMS as a sandbox for untrusted bytecode:** this is not a substitute security boundary.
- **Failing to distinguish optional compatibility code from hard dependencies:** a library that merely checks getSecurityManager may run; a custom Policy engine may require redesign.

## 14. Pre-Production Checklist

- [ ] Recorded JDK vendor/build, baseline JDK, and target JDK.
- [ ] Confirmed Security Manager status by JDK (JDK 17 deprecated, JDK 24+ disabled).
- [ ] Located all `java.security.manager`, `java.security.policy` launch flags and `java.policy` files.
- [ ] Scanned source code, bytecode/dependencies, and test runners for `setSecurityManager`, `Policy`, `AccessController`, and `checkPermission`.
- [ ] Categorized use cases: sandbox, OS resources, authorization, lifecycle testing, or optional compatibility.
- [ ] Documented threat model and list of resources requiring restriction.
- [ ] If untrusted code exists, designed appropriate out-of-process/out-of-JVM boundaries.
- [ ] Processes run under least-privilege users/identities and filesystem/network permissions.
- [ ] Secrets are not provisioned to workers/plugins beyond necessary scope.
- [ ] Business APIs enforce identity, resource, and tenant authorization at the proper places.
- [ ] Tests cover access denial, timeouts, memory/CPU quotas, and process crash isolation.
- [ ] No code installs Security Manager on JDK 24+ along mandatory execution paths.
- [ ] Verified dependencies/plugins/frameworks have versions supporting the target JDK.
- [ ] Updated startup commands, container configs, runbooks, and CI.
- [ ] Executed security tests on a production-equivalent deployment.
- [ ] Logging/auditing/alerting exist for denied permissions and limit-exceeding behavior.
- [ ] Owners, evidence, and handling plans exist for any remaining migration items.

## 15. Official References

- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): context and changes in JDK 17.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): execution changes starting in JDK 24.
- [Oracle Java SE 24 — The Security Manager Is Permanently Disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): specific launcher, API behavior, and migration guidance.
- [Java SE 17 SecurityManager API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html): deprecated-for-removal status in JDK 17.

When cross-checking, prioritize documentation for the **actual release and vendor runtime**. APIs sharing the same name across JDKs can carry different semantics; conclusions must always be verified with actual startup and scenario tests.

## 16. Conclusion

**Security Manager has been deprecated for removal since JDK 17 and permanently disabled starting in JDK 24.** Many related APIs remain present in newer JDKs yet no longer enforce permissions under the former `java.policy` model; some return null or execute directly, while others always throw exceptions. Therefore, migration cannot consist solely of suppressing compiler warnings, catching exceptions, or adding another JVM flag.

To preserve security goals, first identify which resources and code Security Manager was protecting, then move to the right boundaries: OS/container/VM permissions for resources and untrusted code, network/IAM for service access, authorization for business data, and subprocesses for test/lifecycle isolation. Next, verify **denied cases**, not only the happy path. This approach lets you upgrade the JDK without accidentally erasing the defensive layers the legacy system relied on.