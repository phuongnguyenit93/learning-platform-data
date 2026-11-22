# Distinguishing Operating System Permissions From Historical Java Security Mechanisms

## 1. Why Distinguish Two Layers of Protection?

In Java Core I/O, an application reading a file, writing logs, creating a directory, or opening a socket is not governed solely by Java language rules. It runs **inside an operating-system-managed process**, with a concrete account, access permissions, mounts, sandboxes, or system policies.

Historically, Java also had **`SecurityManager` + `Policy` + `Permission` + `AccessController`** to restrict **code running inside the same JVM** according to Java-evaluated permissions. That mechanism differs from filesystem permissions enforced by the OS, and is no longer the path for building new sandboxes:

- In **JDK 17**, `SecurityManager` and related APIs were **deprecated for removal** under **JEP 411**. In JDKs that still support it, when no Security Manager is enabled, the historical policy permission-checking mechanism provides no sandbox layer as many older Java examples describe.
- Starting in **JDK 24**, `SecurityManager` is **permanently disabled** under **JEP 486**: it cannot be enabled via startup flags and no new Security Manager can be installed at runtime; legacy APIs may remain in some versions for compatibility, yet their behavior has changed.
- **Operating system permissions continue to operate normally** in both cases: if the process lacks permission to open a file, the OS/filesystem can deny it even though the JVM has no Security Manager.

This lesson focuses on **safe I/O design**: understanding who actually grants or denies permissions, handling errors properly, managing process identity, constraining paths, and replacing flawed expectations about the historical Java sandbox.

> **Quick rule:** "No `SecurityManager`" does **not** mean Java can read any file. "Having a `FilePermission`" does **not** mean you granted OS-level permission.

## 2. Two Permission Layers: Tracing the Path of a Read Call

A program calls:

```java
String text = Files.readString(
        Path.of("/srv/app/config.txt"),
        StandardCharsets.UTF_8);
```

This is an illustrative snippet using `java.nio.file.Files`, `Path`, and `StandardCharsets`, requiring `IOException` handling. On a modern JVM, the conceptual path is:

```text
Java application
   |
   | Files.readString(path)
   v
Java NIO provider / native filesystem API
   |
   v
Operating system + filesystem + mount
   |
   +-- Process identity: UID/GID, token/privileges...
   +-- File and directory permissions: mode/ACL/ownership
   +-- Read-only mount, sandbox, container, security policy...
   |
   +-- Allow -> reads bytes
   |
   +-- Deny  -> I/O error or provider-appropriate error
```

In an **older JVM with an active Security Manager**, a Java `Permission` check layer could also run before reaching the OS. Yet even when Java permits it, **the OS can still deny access**. Java permissions were an additional control layer, not a "pass" to bypass OS ACLs.

### Comparison Table

| Question | Operating system permissions | Historical Java Security Manager |
|---|---|---|
| Who enforces it? | Kernel/filesystem/OS security subsystem | Permission-checking mechanism inside the Java runtime when enabled |
| Primary identity | User/group/token/process and associated privileges | ProtectionDomain, CodeSource, policy, and stack context |
| Commonly protected objects | Files, directories, sockets, processes, devices, syscalls, mounts | Java operations instrumented to check `Permission` |
| Examples | POSIX mode, ACL, Windows access token + DACL | `FilePermission`, `SocketPermission`, `RuntimePermission` |
| When Java calls `Files.readString` | OS checks open/read capability | Older JDKs **might** check Java permission if Security Manager was enabled |
| Can it bypass OS ACLs? | No: the OS is the final authority on system resources | No |
| Status in JDK 24+ | Still enforced | Security Manager cannot be enabled |
| Protection scope | Processes, users, namespaces, OS-level enforcement | Primarily historical in-JVM sandboxing/code control |

An application may also have **additional** authentication, business authorization, filename constraints, tenant isolation, or library controls. Those layers are **distinct** from both OS permissions and the legacy Security Manager.

## 3. Linux/Unix Filesystem Permissions: Owner, Group, Others

On filesystems supporting the POSIX model, files typically have an owner, group, and permission bits:

```text
-rw-r-----  1 appuser appgroup ... config.txt
 ||| ||| |||
 ||| ||| +++-- others: ---
 ||| +++------ group: r--
 +++---------- owner: rw-
```

Three basic permissions:

- `r` (read): allows reading file contents if path traversal reaches the file and no other control layer forbids it.
- `w` (write): allows modifying file contents when open mode and filesystem conditions allow.
- `x` (execute): on executable files, means running the file; on **directories**, means **traverse/search** entries inside.

**Directory** permissions are especially important:

| Directory permission | Common meaning on POSIX |
|---|---|
| `r` | List entry names when other conditions allow |
| `w` | Modify directory entries: create/delete/rename when combined with required permissions |
| `x` | Access/traverse entry names, needed to pass through a directory when resolving paths |

Consequently, a file with `r--` might still be unreadable if the process lacks traverse permission on a parent directory. Likewise, **deleting or renaming a file** primarily depends on permissions of its containing directory, not simply whether the file itself has the `w` bit. Exact rules also involve sticky bits, ACLs, mount options, ownership, and other protection systems.

### Operating System Tools (Illustrative)

```bash
id
ls -ld /srv/app /srv/app/data
ls -l /srv/app/data/config.txt
stat /srv/app/data/config.txt
getfacl /srv/app/data/config.txt
```

These commands are **Linux/Unix examples**; some may not be installed or may produce varying output across systems. `getfacl` may be unavailable and filesystems may not support identical ACL models. Never run `chmod -R 777` or grant broad permissions just to "fix a Java error."

## 4. Windows Permissions: Access Tokens and ACLs

On Windows, access checks typically evaluate the process/thread's **access token** against the file/folder object's **security descriptor/DACL**; identity can encompass user, groups, integrity level, and specific privileges.

Key concepts to distinguish:

- **Owner:** the identity owning the object, influencing permission administration, though not automatically implying permission for every operation in all cases.
- **DACL/ACE:** allow/deny permission entries for principals; inheritance from parent folders can take effect.
- **Access token:** the identity and privileges the process actually runs with; "logged in with an admin account" does not mean every process runs elevated.
- **UAC, integrity levels, policies:** can impose extra restrictions; do not reduce every `AccessDeniedException` to a single simple ACE.
- **File sharing/locking:** open modes and handles held by other processes can cause rename/delete/open failures even when ACLs appear permissive.

Java NIO's `DosFileAttributeView` (read-only, hidden, system, archive) **is not** Windows' full ACL system. Setting read-only does not replace DACL configuration. To inspect or manage ACLs where supported by the provider, see `AclFileAttributeView`, `AclEntry`, and `UserPrincipalLookupService`.

Checking Windows permissions typically uses OS administrative tools such as `icacls`, PowerShell, and the file/folder Security tab, under the actual service account running the application. Do not infer production server permissions from results on a developer machine.

## 5. How Does Java NIO Inspect/Read Permission Metadata?

Java's `java.nio.file.Files` allows interacting with filesystem attributes **when supported by the provider**:

| API | Purpose |
|---|---|
| `Files.getOwner(path)` | Reads the file's owner |
| `Files.setOwner(path, principal)` | Requests changing the owner; requires OS permission |
| `Files.getPosixFilePermissions(path)` | Reads POSIX permission set if a supporting view exists |
| `Files.setPosixFilePermissions(path, perms)` | Requests updating POSIX mode when permitted |
| `Files.getFileAttributeView(path, PosixFileAttributeView.class)` | Obtains the POSIX attribute management view if supported by provider |
| `Files.getFileAttributeView(path, AclFileAttributeView.class)` | Obtains the ACL view if supported |
| `Files.isReadable(path)` | Preliminary check of whether the JVM can read the file |
| `Files.isWritable(path)` | Preliminary check of writability |
| `Files.readAttributes(path, ...)` | Reads specified attributes through the provider |
| `Files.createTempFile(..., attrs)` | Can create a file with appropriate supported initial attributes |

**Using APIs to view or edit permissions does not give the JVM unlimited file-administration powers.** Calls to `setOwner` or `setPosixFilePermissions` are still checked by the OS. When unsupported, APIs may throw `UnsupportedOperationException` or another exception per contract.

### POSIX Permissions in Java (Illustrative Code)

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;
import java.nio.file.attribute.PosixFilePermission;

Path path = Path.of("/srv/app/secrets.txt");

// Only runs on filesystems/providers supporting POSIX attributes
// and when the process has permission to change permissions.
Set<PosixFilePermission> ownerOnly =
        PosixFilePermissions.fromString("rw-------");

Files.setPosixFilePermissions(path, ownerOnly);
```

This is an **illustrative snippet** that must be inside a method handling `IOException` and applied only to files authorized for management. Never blindly call `setPosixFilePermissions` on system files or mistake `"rw-------"` for an independent application "role."

### Checking the Provider

```java
var view = Files.getFileAttributeView(
        path,
        PosixFileAttributeView.class);

if (view != null) {
    Set<PosixFilePermission> permissions = view.readAttributes().permissions();
    System.out.println(PosixFilePermissions.toString(permissions));
}
```

This snippet requires importing `PosixFileAttributeView`, `PosixFilePermission`, `PosixFilePermissions`, and error handling. `view != null` only means the provider exposes that API for the path; it does not promise subsequent permission changes will succeed.

## 6. `isReadable`/`isWritable` Are Not Authorization Mechanisms

`Files.isReadable(path)` and `Files.isWritable(path)` are often handy for UX or diagnostics, but **they are not immutable security decisions**.

Counter-example:

```java
if (Files.isWritable(target)) {
    Files.writeString(target, content);
}
```

Between `isWritable` and `writeString`:

- ACLs can change.
- The file can be deleted or renamed.
- A symlink can redirect to another target.
- A mount can switch to read-only.
- Another handle or policy can alter operation conditions.

This is **TOCTOU** (time-of-check to time-of-use). A check returning `true` does not guarantee the subsequent operation succeeds. A check returning `false` does not explain why: non-existence, indeterminable state, insufficient access, or an unreliable provider response.

A better pattern in many cases is **performing the permitted operation within controlled boundaries and handling actual exceptions**:

```java
try {
    String text = Files.readString(target, StandardCharsets.UTF_8);
    // Process text per business schema.
} catch (NoSuchFileException ex) {
    // File no longer exists at open/read time.
} catch (AccessDeniedException ex) {
    // Filesystem/provider reported access denied.
} catch (IOException ex) {
    // Other I/O errors.
}
```

This is an illustrative snippet requiring imports and a `target` variable. Not every provider throws the exact `AccessDeniedException` subclass when denied; general `IOException` must be handled too. On JDK 17 with a historical Security Manager enabled, some APIs can also throw `SecurityException` for Java permissions; do not confuse that with OS ACLs.

## 7. How Did Java's Historical `SecurityManager` Work?

In older Java releases, `SecurityManager` was designed to govern certain sensitive actions of Java code via **permission checks**.

Example concepts:

- `java.io.FilePermission`: represented permissions such as `read`, `write`, `execute`, and `delete` on files/paths under Java policy.
- `java.net.SocketPermission`: represented certain network permissions such as connect/accept/listen/resolve in the legacy mechanism.
- `java.lang.RuntimePermission`: permissions for certain runtime capabilities.
- `java.security.Policy`: policy source mapping code origins/protection domains to permissions.
- `java.security.AccessController` and `AccessControlContext`: related to stack-based access checks in the historical model.
- `ProtectionDomain`/`CodeSource`: described code and permission domains in the policy model.

With an active Security Manager, Java I/O calls could pass through `checkRead`/`checkWrite` or `checkPermission` before reaching the OS. If Java policy denied it, code could receive `SecurityException` or a subclass. If Java policy allowed it while the OS denied it, I/O still failed.

**Do not copy Java 8 code with `System.setSecurityManager(new SecurityManager())` as a security recipe for modern applications.** In JDK 17 these APIs are deprecated for removal; from JDK 24 onward the mechanism cannot be enabled.

## 8. Java's `FilePermission` Is Not `chmod` or an ACL

This is a widespread misconception. With `java.io.FilePermission` (historical API):

```java
import java.io.FilePermission;

FilePermission permission =
        new FilePermission("/srv/app/data/report.csv", "read");
```

The code above **only constructs a `Permission` object inside the JVM** for use in the legacy Java security model. It **does not**:

- Invoke `chmod`.
- Set POSIX mode `r--------` or `rw-------`.
- Add an ACE to a Windows ACL.
- Grant filesystem access to the process account.
- Make the OS ignore read-only mounts or policies.
- Automatically enable `SecurityManager`.
- Guarantee the file exists or is readable.

Conversely, `Files.setPosixFilePermissions(path, perms)` requests altering **filesystem permission metadata**, if supported by the provider and allowed by the OS.

Illustrative table:

| Code / concept | Permission-related effect |
|---|---|
| `new FilePermission(path, "read")` | Creates a Java permission object; does not alter OS |
| `Policy` granting `FilePermission` (older JDK with Security Manager) | Can pass the Java policy layer if relevant checks run |
| `chmod 600 secret.txt` on POSIX | Changes file mode when permitted by OS |
| `Files.setPosixFilePermissions(...)` | Changes POSIX permissions via NIO if provider supports it and privileges suffice |
| Windows `icacls` | Inspects/modifies ACLs according to system capabilities and privileges |
| Running service as a low-privilege user | OS restricts which resources the process can access |
| Docker/container mounting a file read-only | Enforces runtime constraints via container/host mechanisms |

The name `Permission` in Java is easily confused with OS "permissions." Always ask: **does this permission belong to the legacy JVM policy layer or to OS metadata/enforcement?**

## 9. JDK 17, JDK 24, and the Direction Forward

The evolution of `SecurityManager` directly affects reading legacy code, READMEs, courses, or older Java tutorials.

| Timeline | Status to know |
|---|---|
| Older Java versions | Included Security Manager and policy mechanisms used in some sandbox/plugin setups |
| JDK 17 — JEP 411 | Security Manager and related APIs **deprecated for removal**; do not use for new designs |
| JDK 18–23 | Continued transition with release-specific changes/warnings; consult exact release docs |
| JDK 24 — JEP 486 | **Permanently disables the Security Manager**; cannot be enabled at startup or runtime |
| Post-JDK 24 | Per migration guidance, native Java Security Manager is not a modern app sandboxing solution; legacy APIs may remain for transition without active policy enforcement |

When checking the actual JVM:

```bash
java -version
```

Do not build new software requiring `-Djava.security.manager=allow` to isolate plugins and expect to run it on JDK 24+: the mechanism **cannot be enabled**. On JDK 17, remaining flags/configurations exist primarily for compatibility and migration, not as long-term architectural advice.

### JEP 411 vs. JEP 486

- **JEP 411 — Deprecate the Security Manager for Removal:** starting in JDK 17, signals warning and planned removal.
- **JEP 486 — Permanently Disable the Security Manager:** JDK 24 blocks activation; related APIs operate in degraded compatibility modes to aid transition.

**"Permanently disabled" does not necessarily mean every API class was immediately deleted from bytecode in JDK 24.** Distinguish "disabling the feature" from "removing classes from the JDK." During migration, check release notes for your target version.

## 10. What Was `AccessController.doPrivileged` Used For?

In the historical Security Manager architecture, stack-based checks inspected protection domains along the call stack. `AccessController.doPrivileged` executed a code block with special access semantics in Java policy evaluation.

Legacy documentation style example:

```java
String value = AccessController.doPrivileged(
        (PrivilegedAction<String>) () -> System.getProperty("user.home"));
```

**This is a historical snippet, not recommended for new code.** It requires importing `AccessController` and `PrivilegedAction`, and the JDK 17 compiler may emit deprecation warnings.

Key distinctions:

- `doPrivileged` does not grant OS file-read privileges to the process.
- It does not bypass UID/GID, Windows DACLs, read-only mounts, or container sandboxes.
- From JDK 24 onward, with Security Manager inactive, common `doPrivileged` overloads simply invoke the action directly as without a Security Manager, no longer acting as an original JVM privilege boundary.
- Do not use `doPrivileged` to "wrap" a file operation throwing `AccessDeniedException`; that is not how system permissions are fixed.

When legacy code overuses `doPrivileged`, plan to **remove dependencies on Security Manager** and design proper process privileges and business authorization rather than merely suppressing compiler warnings.

## 11. No `SecurityManager` Does Not Mean the JVM Is Completely Safe or Completely Unsafe

The Java runtime has safety mechanisms distinct from `SecurityManager`:

- **Type safety, bytecode verification, access modifiers, module boundaries:** protect language/runtime integrity and limit certain interactions.
- **OS permissions, process accounts, filesystem permissions, networking controls:** actually enforce access to system resources.
- **Application authentication and authorization:** decide which user/tenant may perform business actions.
- **Cryptography, TLS, key management:** protect confidentiality, integrity, and protocol authentication.
- **Process isolation / containers / VMs:** create stronger boundaries around less-trusted programs.

These mechanisms address **different classes of risk** and do not all substitute for one another.

A `private` class does not prevent code inside the same OS-privileged process from reading a password file if I/O capability exists and is invoked improperly. Conversely, protecting a file with mode `600` does not stop the authorized application itself from accidentally logging secrets or returning them to the wrong tenant.

These are two independent verification layers: **business authorization** and **process authority**.

## 12. Choosing Process Identity by Least Privilege

Rather than relying on Java policy to forbid individual libraries, run applications with the **minimum operating system privileges required to do their job**.

Example service that only needs to read configuration files and write logs:

```text
Process identity: app-service

Allowed:
  /etc/my-app/config.yaml       read
  /var/lib/my-app/data/         read/write per business logic
  /var/log/my-app/              append/write per policy
  outbound network              only permitted destinations if egress-controlled

Not necessary:
  /root/, other user homes, /etc/shadow
  /var/run/docker.sock
  host device nodes
  broad chown/chmod privileges
```

A production deployment can use:

- A dedicated service user, avoiding root/Administrator unless strictly required.
- POSIX modes + ACLs or Windows DACLs tailored to actual directories/files.
- Containers running as non-root; avoiding sensitive host directory mounts and privileged containers.
- Read-only root filesystems when the application only needs a few writable directories.
- Restricted network egress/ingress, capabilities, and namespaces per platform.
- Secret injection with narrow secret-file read permissions; never bake secrets directly into artifacts.
- Audit logs and monitoring for `AccessDeniedException` without logging secret contents.

**A process user inside a container does not automatically match a user on the host.** UID mapping, volume mounts, Kubernetes `securityContext`, SELinux/AppArmor, and platform configurations must be verified per environment.

### The Danger of "Running as Admin to Silence `AccessDenied`"

Elevating privileges for the entire JVM may make an error disappear temporarily, yet **expands the blast radius** if the application suffers path traversal, deserialization vulnerabilities, or a compromised dependency. Fix permissions specifically on the required directory or relocate storage appropriately rather than elevating the whole process.

## 13. Complete Java 17+ Example: File Operations and Explaining Permission Boundaries

The following program runs **without `SecurityManager`**. It creates a temporary file in an OS-permitted directory, writes and reads using NIO, and then illustrates a **purely lexical** path check. The example does **not** force a permission error by altering OS permissions, since behavior varies across OSes, users, and ACLs.

Save as **`OsVsJavaPermissionsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class OsVsJavaPermissionsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("os-permissions-");
        Path file = directory.resolve("record.txt");

        try {
            Files.writeString(
                    file,
                    "approved-data\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            String loaded = Files.readString(
                    file, StandardCharsets.UTF_8);

            Path relative = Path.of("reports", "..", "record.txt");
            Path candidate = directory.resolve(relative).normalize();

            System.out.println("Read: " + loaded.strip());
            System.out.println("Lexically within directory: "
                    + candidate.startsWith(directory));
            System.out.println("Same normalized target: "
                    + candidate.equals(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run:

```bash
javac OsVsJavaPermissionsDemo.java
java OsVsJavaPermissionsDemo
```

**Exact stdout if the OS allows creating, reading, writing, and deleting in the temp directory:**

```text
Read: approved-data
Lexically within directory: true
Same normalized target: true
```

Explanation:

1. `Files.createTempDirectory` asks the OS for permission to create a new temporary directory. If the temp directory is not writable, the program can throw `IOException` before printing anything.
2. `CREATE_NEW` creates a non-existent file, avoiding accidentally truncating an existing `record.txt`. It does not by itself provide a sandbox against path attacks outside trusted directories.
3. `Files.readString` reads through the provider under the process's actual permissions. No Java `FilePermission` is used to "grant" OS permission.
4. `normalize()` collapses `reports/..` at the path-string level; `startsWith(directory)` returns `true` for this simple example.
5. **The lexical check above is not proof against symlinks/TOCTOU.** It demonstrates only a preliminary filtering technique; never use `normalize()+startsWith()` alone as a complete security boundary against attacker-controlled paths.
6. All temp resources are deleted in `finally` during normal execution. On abrupt kill/crash, `finally` may not run; production apps need additional cleanup strategies.

This code is standalone, targets Java 17+ with no admin actions, and excludes `SecurityManager` because it is not a foundation for new applications.

## 14. POSIX `FileAttributeView`: Creating Private Files From the Start

If a secret-storing file runs on a provider supporting POSIX, request attributes **when creating the file** rather than creating it with broad permissions and restricting them afterward:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileAttribute;
import java.nio.file.attribute.PosixFilePermissions;

Path directory = Path.of("/srv/app/secrets");

FileAttribute<?> ownerOnly =
        PosixFilePermissions.asFileAttribute("rw-------");

Path secret = Files.createTempFile(
        directory,
        ".secret-",
        ".tmp",
        ownerOnly);
```

This is an **illustrative snippet**, not standalone runnable; the directory must exist with creation permissions, and the provider must support POSIX attributes. On Windows filesystems/views without POSIX support, requesting those attributes can throw `UnsupportedOperationException`. Choose appropriate Windows ACL measures rather than catching `IOException` and falling back to creating a secret file with broad default permissions.

**Benefit:** setting permissions inside the file-creation operation (when supported by the provider) avoids a window during which a sensitive file exists with overly broad permissions before `setPosixFilePermissions` runs.

Still, effective read/write access can be constrained by ACLs/mounts/SELinux, and root/elevated principals may have additional rights. `rw-------` does not guarantee "no other user on earth can access it by any mechanism."

### When the Filesystem Lacks a POSIX View

Do not hardwire cross-platform apps to `PosixFilePermissions` without checking the environment. You can:

1. Define the file's security requirements.
2. Check supported views/providers.
3. If "owner-only" is mandatory yet unconfigurable, **fail closed** instead of creating a sensitive file with uncontrolled permissions.
4. Use the OS's native secret-storage/ACL mechanisms or deploy in an environment with suitable isolation.

## 15. `AccessDeniedException`, `SecurityException`, and Other Errors

Commonly misunderstood Java I/O errors:

| Error type | Typical meaning | Always from Java SecurityManager? |
|---|---|---|
| `AccessDeniedException` | Filesystem/provider reports access to path is not permitted | No |
| `FileSystemException` | Filesystem problem; may carry `reason`/`otherFile` | No |
| `NoSuchFileException` | Entry does not exist during operation | No |
| `FileAlreadyExistsException` | Creating a new entry with an already-existing name | No |
| `SecurityException` | API/runtime-specific permission/control error; in older JDKs could come from security manager | Must not be assumed to mean OS ACL |
| `UnsupportedOperationException` | Provider/API does not support the requested operation/attribute view | No |
| `IOException` | Broader I/O error family | No |

`Files.*` methods often mention `SecurityException` in historical docs for when a Security Manager was active. On JDK 24+, do not use the presence of that documentation clause to conclude a Java policy is protecting files. Conversely, when the OS denies access, code typically receives an I/O exception subclass; handle according to provider and actual message.

**Never write logic like: "Catch `SecurityException` and grant `FilePermission` to fix it."** Real access provisioning must be resolved via OS/admins or application policy, never silently escalated by unprivileged code.

### Safe Logging

Log useful context: operation, error code, redacted path where needed, service principal per observability policies, and correlation ID. Never dump secret file contents, passwords, or access tokens to diagnose permission failures.

## 16. Path Traversal Is an Application Bug, Not an OS Permissions Bug

Suppose a web endpoint accepts a filename from a user:

```text
GET /download?file=invoice.pdf
```

If used directly:

```java
Path target = root.resolve(userInput);
byte[] bytes = Files.readAllBytes(target);
```

an attacker can try `../secret.txt` or its equivalent on the target OS.

If the process **has OS permission** to read that secret file, the OS will not deny it just because the HTTP caller lacks authorization. The kernel sees **a request from the process account**, unaware of which HTTP user asked for it.

The application must enforce:

1. Authenticating user/request identity.
2. Authorizing by tenant/document ID and business state.
3. Avoiding arbitrary paths as authority objects; preferably map authenticated IDs to application-managed files.
4. Constraining to a fixed root, distinguishing files from directories, and preventing symlink escapes.
5. Addressing check-to-open races, especially in attacker-writable directories.
6. Still running the process under a least-privilege account so the OS blocks paths outside the service's scope.

### Lexical Checks: Necessary but Insufficient

```java
Path base = root.toAbsolutePath().normalize();
Path candidate = base.resolve(userProvidedName).normalize();

if (!candidate.startsWith(base)) {
    throw new IllegalArgumentException("Path outside allowed root");
}
```

This is an illustrative snippet. It catches certain `..` cases after normalization, but **does not prove the real path lies within the root** if an attacker can create or modify symlinks or files in the directory. You must also enforce absolute-input policies, case/volume semantics, and consistent encoding/canonicalization.

If the provider supports `SecureDirectoryStream`, certain operations can be executed relative to a directory handle to reduce rename/symlink races. Not every provider supports it; stronger designs generally combine restricted directory permissions, preventing attackers from altering namespaces, file-descriptor/handle checks, and OS isolation. Never call `toRealPath()` once and assume the path stays immutable for all later I/O.

## 17. Temporary Directories, Sensitive Files, and Symlinks

`Files.createTempFile` is a better API than manually composing names like `secret-<timestamp>.tmp` because it creates a new file with a unique name under provider semantics, reducing collisions.

Safe design also requires:

- Choosing a **trusted directory** with permissions suited to the service account.
- When creating secret files, ensuring appropriate permissions/ACLs **at creation time** if supported by the provider.
- Avoiding fixed names in world-writable directories without race-mitigation strategies.
- Not defaulting to `/tmp` for long-lived secret storage; understand sticky bits, cleanup policies, and OS permissions.
- Not passing a temp path to another process while assuming it cannot modify contents before the file is read back.
- Controlling symlinks/hardlinks and file replacements along paths an attacker can influence.
- Closing file handles and ensuring data is not published before validation.
- When replacing critical files, considering write-temp-then-rename, atomic move where supported, and separate durability requirements.

Note: **atomic rename, file permissions, and application access control are three independent concerns**. An atomically renamed file can still carry wrong ACLs; a file with right ACLs can still hold invalid business data; an app authenticating users properly still needs filesystem race protection.

## 18. Do Not Rely on a "Java Sandbox" to Run Untrusted Plugins

A frequent request is "run user-submitted Java code without letting it read files." Older Java versions had an in-JVM sandbox model built on `SecurityManager`. In modern Java:

- Do not use `SecurityManager` as a new security boundary; from JDK 24 onward it cannot be enabled.
- A single JVM is generally not a suitable security boundary for executing arbitrary code with access to powerful APIs.
- `ClassLoader`, module access, Java visibility, and bytecode verification do not provide an equivalent barrier preventing untrusted code from reaching OS resources.
- You need **process/OS-level isolation** with least-privilege accounts, filesystem namespaces/mounts, sandboxes/containers/VMs, network policies, CPU/memory/time quotas, and monitoring.
- For genuinely untrusted code, a container alone does not automatically create strong isolation if run privileged, mounting host sockets, granting high capabilities, or disabling security restrictions.
- Never keep production secrets inside the same filesystem namespace or environment as a process running untrusted code without compelling necessity.
- Manage child process cleanup, timeouts, stdout/stderr, quotas, and prevent children from accessing runtime/host control sockets.

Programmatic mechanisms restricting "which APIs may be called" can still help enforce **business rules**, but must never be advertised as a hardened sandbox against an attacker able to run arbitrary bytecode under the process's OS privileges.

## 19. Application User Authentication and Authorization Is the Third Layer

A server running as `app-service` might be able to read the entire `/var/lib/app/orders` directory. Yet when Alice calls `GET /orders/123`, whether Alice is permitted to view order 123 must be decided by the application:

```text
HTTP request from Alice
   |
   v
Authentication: Who is Alice?
   |
   v
Authorization: Is Alice allowed to view order 123?
   |
   v
Obtain path from ID verified against domain model
   |
   v
Filesystem open/read under OS permissions of app-service
   |
   v
Response contains only permitted disclosure data
```

The OS does not know "order 123 belongs to Alice." If the application skips the authorization step, the file read still succeeds because the service process is permitted. That is an **IDOR / broken object-level authorization** vulnerability, which cannot be solved simply via `chmod` for a shared service user.

In multi-tenant systems:

- Map tenant + resource ID on the server side.
- Enforce authorization on every read/write/delete operation.
- Avoid using raw filenames or paths as client-editable object IDs.
- Scope worker/service accounts to required data directories, or isolate per tenant when requirements are high.
- Audit data access with both the application actor **and** process/service identity without conflating the two identities.

## 20. ACLs in Java NIO: How Do They Differ From POSIX Modes?

`AclFileAttributeView` lets you work with a list of `AclEntry` objects when supported by the filesystem:

```java
AclFileAttributeView view = Files.getFileAttributeView(
        path,
        AclFileAttributeView.class);

if (view != null) {
    List<AclEntry> entries = view.getAcl();
    for (AclEntry entry : entries) {
        System.out.println(entry.principal() + ": " + entry.permissions());
    }
}
```

This is an illustrative snippet requiring `AclFileAttributeView`, `AclEntry`, `List`, `Files`, `Path`, and `IOException` handling; `path` is assumed declared.

Do not conclude:

- `getAcl()` returning a list means Windows ACLs are modeled identically to POSIX `rwx`.
- ACE order/type does not affect permission evaluation; ACLs have complex evaluation rules.
- Every provider permits `setAcl`.
- You can "grant permissions" simply by constructing `AclEntryPermission.READ_DATA` in an enum set without updating metadata.
- Copying an ACL verbatim from one OS to another always preserves semantics.

Modifying ACLs requires understanding principals, allow/deny ACEs, inheritance, and rights to modify security descriptors on the target platform. Never automatically add an `ALLOW ALL` entry to work around write errors in production.

## 21. Directory Permissions and Atomic File Updates

Suppose an application updates a configuration file safely:

1. Create a temporary file in the destination directory.
2. Write new data and validate it.
3. Sync the temporary file if durability is required.
4. Move the temporary file to replace the destination via atomic rename when supported.
5. Verify/preserve appropriate permissions on the new file; clean up temp on failure.

The OS checks multiple distinct capabilities:

- Creating the temp file requires appropriate permissions on the **directory**.
- Writing contents requires permission to open/write the **file**.
- Renaming/replacing requires permissions on directory entries and may depend on ACLs/handles.
- Syncing data may be constrained by the provider/filesystem.
- Changing owner or ACL of the new file is not granted to a process by default.

One notable detail: when creating a **new temporary file and replacing the destination**, the temp file's owner/ACL metadata can become the metadata of the file at the destination name. Do not assume an atomic replace automatically preserves old ACLs. Set the appropriate metadata **before** publishing if required by the problem.

**Do not have Java manually delete the destination and then rename the temp file** to "bypass permission errors." That risks losing the old version, creates a gap visible to readers, and still fails if the OS denies it.

## 22. Differences Between Java Modules/Security and OS Access Control

The Java Platform Module System (`module-info.java`) lets you declare `requires`, `exports`, `opens`, etc., to control code/package accessibility across module boundaries. It **is not** a file-read authorization system.

Example:

```java
module com.example.viewer {
    requires java.base;
}
```

This is a `module-info.java` example, not a standalone runnable program. Module `java.base` is implicitly read by default; the declaration merely illustrates syntax.

Do not infer that omitting `requires java.io` prevents code from reading the filesystem: `java.io` is a **package** inside `java.base`, not a separate module. Nor do `exports` or `opens` represent OS permissions. Java module boundaries target encapsulation, readability, and reflective access constraints; I/O permission boundaries require OS/process/application policies.

Similarly, `private`, `protected`, classpath isolation, and package visibility do not create a filesystem sandbox against code executing inside the same JVM and OS principal.

## 23. Diagnosing Real Errors With a Troubleshooting Table

| Symptom | Possibilities to check | What not to do |
|---|---|---|
| `AccessDeniedException` reading a file | Process user, ACL/owner, parent dir traverse, mount, sandbox, lock/provider | Create `new FilePermission` thinking the OS grants access |
| File write denied on Linux | File mode/ACL, dir permissions, read-only mount, SELinux/AppArmor | Immediately run the whole app as root |
| File has `rw-------` yet another process reads it | Actual owner, elevated privileges, namespace, ACL, shared hardlinks, copied data | Treat mode bits as encryption |
| `SecurityException` in Java 8/17 code with manager | Java policy/permission check, Security Manager config, classpath | Immediately assume missing `chmod` |
| `System.setSecurityManager` fails on JDK 24+ | JEP 486 permanently disabled the feature | Hunt for a flag to "turn it back on" |
| `Files.isReadable` true yet read fails | TOCTOU, mount/provider, race, share/lock, path swapped | Treat the probe as authoritative authorization |
| One HTTP user views another user's file | Application authorization, tenant isolation, path traversal | Only tweak Java SecurityManager policy |
| Arbitrary plugin reads secrets | Same process account/namespace, missing OS isolation | Rely solely on `ClassLoader` for sandboxing |
| POSIX permission API unsupported | Filesystem/provider lacks the view | Ignore private-file requirements and still publish |
| Container still sees host secrets | Volume mounts, root/capabilities, `securityContext` | Assume "using Docker" is enough |

## 24. Practice: Designing Controlled Verification Tests

Tests should separate OS behavior from Java mechanisms:

**Exercise 1 — Different process users.** Create a data file in a lab environment and set mode/ACL readable only by service A. Run **two real processes** under two appropriate accounts/groups and test `Files.readString`. Do not alter real system files or production secrets.

**Exercise 2 — Directory traversal permission.** Grant read permission on a file while removing traverse permission on a parent directory in a POSIX test environment; observe file-opening behavior. Restore permissions afterward so you do not lock yourself out.

**Exercise 3 — Probe vs. operation.** Check `Files.isReadable` and then attempt reading; discuss why the two moments can differ. Do not introduce real races by swapping symlinks outside a test directory.

**Exercise 4 — Historical Java policy limits.** Read the JDK 17/JEP 411 and JDK 24/JEP 486 documentation; note what role `FilePermission` used to play and why it is no longer used for sandboxing in modern Java. Do not install a Security Manager on a production system just to experiment.

**Exercise 5 — Path traversal.** Write a function resolving filenames inside an application-controlled staging directory. Test `file.txt`, `../file.txt`, absolute paths, and symlinks. Identify where lexical checks filter inputs without replacing symlink-race protection.

**Exercise 6 — Containers.** Run a test service with a read-only root filesystem and a properly permissioned writable volume. List every path needing writes: temp, logs, cache, uploads. Resolve errors by intentionally fixing mounts/ACLs rather than enabling privileged containers.

**Exercise 7 — Testing new secret files.** On a suitable POSIX view, create files immediately with owner-only attributes; on Windows use an equivalent ACL policy. Verify there is no window in which the file sits in a shared folder with overly broad default permissions.

## 25. Self-Check Questions

**1.** Without a Security Manager, can `Files.readString` always read any file?  
**No.** The OS/filesystem/mount continues enforcing the process's permissions.

**2.** Is `new FilePermission(path,"read")` equivalent to `chmod u+r path`?  
**No.** It is merely a Java `Permission` object from the legacy model; it does not modify POSIX modes.

**3.** From which JDK onward is Security Manager permanently disabled?  
**JDK 24**, under JEP 486. JDK 17 deprecated it for removal under JEP 411.

**4.** Does `AccessController.doPrivileged` allow an OS-unprivileged process to read `/etc/shadow`?  
**No.** It does not change OS identity or ACLs.

**5.** On POSIX, why can a file with the read bit set still fail to open?  
**Possibly** missing traverse permission on a parent directory, ACL/mount/OS policy restrictions, or the process identity does not match that permission bit.

**6.** Does `Files.isReadable(path) == true` guarantee a file-open call one second later will succeed?  
**No.** Races/TOCTOU and system conditions can change.

**7.** A service process is allowed by the OS to read all tenant files. If the API skips tenant checks, will the OS automatically stop Alice from reading Bob's file?  
**Not by application tenant logic.** The OS sees the service process; the application must enforce authorization itself.

**8.** Can `ClassLoader` or JPMS replace `SecurityManager` to sandbox untrusted bytecode?  
**Not as a full OS security boundary.** Appropriate process/OS/container/VM isolation is required.

**9.** Does a `rw-------` file guarantee nobody can obtain the data if the app runs as root and logs all contents?  
**No.** OS modes do not protect against privileged/authorized processes or application-layer data leaks.

**10.** When using a temp file and atomic rename to replace a target, is the new file guaranteed to keep the old ACL?  
**No.** The published object is the new file and may carry the temp file's metadata; a permission-preservation policy is needed.

## 26. Secure Java I/O Design Checklist

Before deploying or reviewing read/write systems:

- [ ] Identify the actual **process account** running the JVM.
- [ ] Identify which resources require read, write, create, delete, or rename, and grant least privilege.
- [ ] Check **parent directory** permissions, not just file permissions.
- [ ] Understand the filesystem/provider and OS: POSIX mode/ACL, Windows DACL, mounts, and sandboxes.
- [ ] Do not rely on `FilePermission` or historical `SecurityManager` to grant or manage OS access.
- [ ] Understand JDK 17 deprecation and JDK 24 permanent disabling of `SecurityManager`.
- [ ] Authenticate and authorize **business users** before mapping IDs to paths.
- [ ] Mitigate path traversal and symlinks; never rely solely on `normalize()+startsWith()` against attackers.
- [ ] Never use `isReadable`/`isWritable` as a guarantee of success or final security check.
- [ ] Perform actual I/O inside `try/catch` and handle `IOException` contextually.
- [ ] Create sensitive files with appropriate permissions/ACLs from the start when supported.
- [ ] Isolate namespaces/processes if executing plugins or untrusted code.
- [ ] Never run the JVM as root/Administrator solely to bypass ACL checks.
- [ ] When using containers, audit mounts, users, capabilities, and secret exposure.
- [ ] When publishing temp files, address atomicity, ACL metadata, and durability **independently**.
- [ ] Test on the actual deployment OS/filesystem rather than extrapolating from a developer machine.
- [ ] Never log secrets inside permission errors or I/O exceptions.
- [ ] Conduct security reviews whenever changing file permissions, tokens, sandboxes, or service principals.

## 27. Summary

- **Operating system permissions** are enforced by the kernel, filesystem, access tokens, ACLs, and mounts, determining whether a process can access system resources.
- **Historical Java Security Manager** was an in-JVM permission-checking layer that **never replaced OS permissions**; `FilePermission` was a Java policy representation, not a `chmod`/ACL operation.
- **JDK 17:** Security Manager deprecated for removal (JEP 411). **JDK 24+:** Security Manager permanently disabled (JEP 486); never build new sandboxes on it.
- **Applications must enforce per-user/per-tenant authorization themselves**; the OS process account has no awareness of per-request business authorization.
- **`Files.isReadable`/`isWritable` are probes, not authority**; filesystem races, symlinks, and path traversal require dedicated design mitigations.
- **Least privilege + OS/process isolation + data/path validation + I/O lifecycle management** form the practical foundation for safe Java I/O.

### Official References

- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411)
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486)
- [Oracle: The Security Manager Is Permanently Disabled, JDK 25](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html)
- [Oracle: SecurityManager, Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/SecurityManager.html)
- [Java FilePermission (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FilePermission.html)
- [Java Files API (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [PosixFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html)
- [AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html)
- [SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html)
