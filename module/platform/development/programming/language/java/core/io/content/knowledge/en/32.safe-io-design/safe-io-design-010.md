# Distinguishing OS Permissions from Historical Java Security Mechanisms

## 1. Why Must You Distinguish These Two Protection Layers?

In Java Core I/O, an application reading files, writing logs, creating directories, or opening sockets is not governed solely by Java language rules. It executes **inside an operating-system-managed process**, with a specific account, access permissions, mounts, sandboxes, or system policies.

Historically, Java also had **`SecurityManager` + `Policy` + `Permission` + `AccessController`** to restrict **code running inside the same JVM** according to Java-evaluated permissions. That mechanism is separate from filesystem permissions enforced by the operating system, and is no longer the way to build modern sandboxes:

- In **JDK 17**, `SecurityManager` and related APIs were **deprecated for removal** under **JEP 411**. Even on JDKs where it still exists, when no Security Manager is enabled, the historical permission-checking policy mechanism does not provide the sandbox layer described in many older Java examples.
- Starting in **JDK 24**, `SecurityManager` is **permanently disabled** under **JEP 486**: it cannot be enabled via startup options and a new Security Manager cannot be installed at runtime; legacy APIs remain in some versions for compatibility, but their behavior has changed.
- **Operating system permissions continue working normally** in both cases: if the process lacks permission to open a file, the OS/filesystem will refuse even without a JVM Security Manager.

This lesson focuses on **safe I/O design**: understanding who actually grants/denies access, handling errors properly, managing process identity, constraining paths, and replacing outdated expectations about historical Java sandboxes.

> **Rule to remember immediately:** “No `SecurityManager`” does **not** mean Java can read any file. “Having `FilePermission`” does **not** mean you granted OS-level permission.

## 2. Two Permission Layers: Visualizing the Path of a Read Call

A program calls:

```java
String text = Files.readString(
        Path.of("/srv/app/config.txt"),
        StandardCharsets.UTF_8);
```

This is an illustrative snippet using `java.nio.file.Files`, `Path`, and `StandardCharsets`, requiring `IOException` handling. On a modern JVM, the high-level path is:

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
   +-- Allowed -> bytes are read
   |
   +-- Denied  -> I/O error or provider-appropriate error
```

In an **older JVM with an active Security Manager**, there could also be a Java `Permission` check layer before reaching the OS. Yet even when Java allows it, **the OS still retains the right to refuse**. A Java permission is an extra control layer, not a “free pass” to bypass OS ACLs.

### Comparison Table

| Question | Operating System Permissions | Historical Java Security Manager |
|---|---|---|
| Who enforces it? | Kernel/filesystem/OS security subsystem | Permission-checking mechanism inside the Java runtime when enabled |
| Primary identity | User/group/token/process and associated privileges | `ProtectionDomain`, `CodeSource`, policy, and call-stack context |
| Typical protected objects | Files, directories, sockets, processes, devices, syscalls, mounts | Java operations instrumented to check `Permission` |
| Examples | POSIX modes, ACLs, Windows access tokens + DACLs | `FilePermission`, `SocketPermission`, `RuntimePermission` |
| When Java calls `Files.readString` | OS checks open/read capability | Older JDKs **might** check Java permission if Security Manager is enabled |
| Can it bypass OS ACLs? | No: the OS is the final arbiter over resources | No |
| Status in JDK 24+ | Still enforced | Security Manager cannot be enabled |
| Protection scope | Process, user, namespace, OS-level enforcement | Primarily intended sandbox/in-JVM code control under the historical model |

An application may also have **additional** authentication, business authorization, filename limits, tenant isolation, or library-level controls. Those layers are **distinct** from both OS permissions and the legacy Security Manager.

## 3. Filesystem Permissions on Linux/Unix: Owner, Group, Others

On filesystems supporting the POSIX model, a file typically has an owner, group, and permission bits:

```text
-rw-r-----  1 appuser appgroup ... config.txt
 ||| ||| |||
 ||| ||| +++-- others: ---
 ||| +++------ group: r--
 +++---------- owner: rw-
```

Three basic permissions:

- `r` (read): allows reading file contents if path traversal reaches the file and no other control blocks it.
- `w` (write): allows modifying file contents when the open mode and filesystem conditions permit.
- `x` (execute): for executables, means running the file; for **directories**, means **traversing/searching** entries inside.

**Directory** permissions are especially important:

| Directory Permission | Typical Meaning on POSIX |
|---|---|
| `r` | List entry names when other conditions allow |
| `w` | Modify directory entries: create/delete/rename when combined with required permissions |
| `x` | Access/traverse entry names, required to pass through the directory when resolving paths |

Consequently, a file with `r--` might still be unreadable if the process lacks traverse permission on a parent directory. Likewise, **deleting/renaming a file** mainly depends on permissions on the containing directory, not whether the file itself has the `w` bit. Exact rules also involve sticky bits, ACLs, mount options, ownership, and other protection subsystems.

### OS Inspection Tools (Illustrative)

```bash
id
ls -ld /srv/app /srv/app/data
ls -l /srv/app/data/config.txt
stat /srv/app/data/config.txt
getfacl /srv/app/data/config.txt
```

These commands are **Linux/Unix examples**; they may not all be installed or may produce different output depending on the system. `getfacl` may be absent and filesystems may support different ACL types. Never run `chmod -R 777` or grant broad permissions just to “fix a Java error”.

## 4. Windows Permissions: Access Tokens and ACLs

On Windows, access checks typically rely on the process/thread **access token** and the file/folder **security descriptor/DACL**; identities may include users, groups, integrity levels, and specific privileges.

Several concepts to distinguish:

- **Owner**: the identity owning the object, which affects permission administration yet does not mean every operation is permitted under all conditions.
- **DACL/ACE**: allow/deny entries for principals; inheritance from parent directories can take effect.
- **Access token**: the actual identity and privileges the process is running with; “logged in as an admin account” does not mean a process always runs with full elevated privileges.
- **UAC, integrity levels, policies**: can impose additional restrictions; do not reduce every `AccessDeniedException` to a single simple ACE.
- **File sharing/locking**: open modes and handles held by other processes can cause rename/delete/open to fail even when the ACL appears to allow it.

Java NIO's `DosFileAttributeView` (read-only, hidden, system, archive) **is not** the full Windows ACL model. Marking read-only does not replace DACL configuration. To work with ACLs when supported by the provider, see `AclFileAttributeView`, `AclEntry`, and `UserPrincipalLookupService`.

Windows permissions are normally inspected using OS admin tools such as `icacls`, PowerShell, and the file/folder Security tab, using the actual service account running the app. Never extrapolate permissions on a production server from results on a developer machine.

## 5. How Does Java NIO Inspect/Read Permission Metadata?

Java `java.nio.file.Files` lets you interact with filesystem attributes **when supported by the provider**:

| API | Purpose |
|---|---|
| `Files.getOwner(path)` | Reads the file's owner |
| `Files.setOwner(path, principal)` | Requests changing the owner; requires OS permission |
| `Files.getPosixFilePermissions(path)` | Reads POSIX permissions if a supporting view exists |
| `Files.setPosixFilePermissions(path, perms)` | Requests updating POSIX mode when permitted |
| `Files.getFileAttributeView(path, PosixFileAttributeView.class)` | Obtains the POSIX attribute view if supported by the provider |
| `Files.getFileAttributeView(path, AclFileAttributeView.class)` | Obtains the ACL view if supported |
| `Files.isReadable(path)` | Preliminary check of whether the JVM can read the file |
| `Files.isWritable(path)` | Preliminary check of writability |
| `Files.readAttributes(path, ...)` | Reads specified attributes via the provider |
| `Files.createTempFile(..., attrs)` | Can create a file with appropriate initial attributes if supported |

**Using APIs to view/modify permissions does not grant the JVM unlimited file-administration powers.** Calls to `setOwner` or `setPosixFilePermissions` are still checked by the OS. When unsupported, APIs may throw `UnsupportedOperationException` or other contract-defined exceptions.

### POSIX Permissions in Java (Illustrative Code)

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;
import java.nio.file.attribute.PosixFilePermission;

Path path = Path.of("/srv/app/secrets.txt");

// Runs only on filesystems/providers supporting POSIX attributes
// and when the process has permission to change permissions.
Set<PosixFilePermission> ownerOnly =
        PosixFilePermissions.fromString("rw-------");

Files.setPosixFilePermissions(path, ownerOnly);
```

This is an **illustrative snippet** that must be inside a method handling `IOException` and applied to an object the process is authorized to administer. Never blindly apply `setPosixFilePermissions` to system files or confuse `"rw-------"` with an independent application “role”.

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

This is a snippet requiring imports for `PosixFileAttributeView`, `PosixFilePermission`, `PosixFilePermissions`, and error handling. `view != null` only indicates the provider exposes that API for the path; it does not promise subsequent permission changes will succeed.

## 6. `isReadable`/`isWritable` Are Not Authorization Mechanisms

`Files.isReadable(path)` and `Files.isWritable(path)` are often handy for UX or observation, yet they are **not immutable security decisions**.

Counter-example:

```java
if (Files.isWritable(target)) {
    Files.writeString(target, content);
}
```

Between `isWritable` and `writeString`:

- ACLs may change.
- The file may be deleted/renamed.
- A symlink may be retargeted.
- A mount may switch to read-only.
- Another handle or policy may alter operation conditions.

This is **TOCTOU** (time-of-check to time-of-use). A `true` check does not guarantee the subsequent operation succeeds. A `false` check also does not tell you exactly why: non-existence, indeterminable state, insufficient access, or an unreliable provider response.

A better pattern in many cases is **attempting the permitted operation within controlled boundaries and handling actual exceptions**:

```java
try {
    String text = Files.readString(target, StandardCharsets.UTF_8);
    // Process text according to business schema.
} catch (NoSuchFileException ex) {
    // File no longer exists at open/read time.
} catch (AccessDeniedException ex) {
    // Filesystem/provider reported access denied.
} catch (IOException ex) {
    // Other I/O errors.
}
```

This is an illustrative snippet requiring imports and a `target` variable. Not every provider throws the exact `AccessDeniedException` subclass on refusal; general `IOException` must also be handled. On JDK 17 with a legacy Security Manager enabled, some APIs could also throw `SecurityException` for a Java permission; never confuse it with an OS ACL.

## 7. How Did Java's Historical `SecurityManager` Work?

In older Java releases, `SecurityManager` was designed to govern certain sensitive actions by Java code via **permission checks**.

Example concepts:

- `java.io.FilePermission`: represented permissions like `read`, `write`, `execute`, `delete` on files/paths per Java policy.
- `java.net.SocketPermission`: represented certain network permissions like connect/accept/listen/resolve in the legacy model.
- `java.lang.RuntimePermission`: permissions for certain runtime capabilities.
- `java.security.Policy`: policy source mapping code sources/protection domains to permissions.
- `java.security.AccessController` and `AccessControlContext`: involved in stack-based access checks in the historical model.
- `ProtectionDomain`/`CodeSource`: described code and permission domains in the policy model.

With an active Security Manager, Java I/O calls could go through `checkRead`/`checkWrite` or `checkPermission` before reaching the OS. If Java policy refused, code could receive `SecurityException` or a subclass. If Java policy allowed it yet the OS refused, I/O still failed.

**Do not copy Java 8 recipes with `System.setSecurityManager(new SecurityManager())` to configure security in new applications.** In JDK 17 these APIs were deprecated for removal; from JDK 24 onward the mechanism cannot be enabled.

## 8. Java's `FilePermission` Is Not `chmod` or an ACL

This is a widespread misinterpretation. With `java.io.FilePermission` (a historical API):

```java
import java.io.FilePermission;

FilePermission permission =
        new FilePermission("/srv/app/data/report.csv", "read");
```

The snippet above **merely constructs a `Permission` object inside the JVM** for use in the legacy Java security model. It **does not**:

- Invoke `chmod`.
- Set POSIX mode `r--------` or `rw-------`.
- Add an ACE to a Windows ACL.
- Grant access to the process account.
- Make the OS bypass a read-only mount or policy.
- Enable `SecurityManager` by itself.
- Guarantee the file exists or is readable.

Conversely, `Files.setPosixFilePermissions(path, perms)` requests changing **filesystem permission metadata**, if supported by the provider and allowed by the OS.

Illustrative table:

| Code / Concept | Permission-Related Outcome |
|---|---|
| `new FilePermission(path, "read")` | Creates a Java permission object; does not modify the OS |
| `Policy` granting `FilePermission` (older JDK with Security Manager) | Can allow passage through the Java policy layer if the relevant check runs |
| `chmod 600 secret.txt` on POSIX | Changes the file's mode when allowed by the OS |
| `Files.setPosixFilePermissions(...)` | Updates POSIX permissions via NIO if provider supports it and privileges suffice |
| Windows `icacls` | Inspects/modifies ACLs according to system capabilities and privileges |
| Running service as a low-privilege user | OS restricts which resources the process can use |
| Docker/container read-only file mount | Runtime environment enforces constraints via container/host mechanisms |

The word `Permission` in Java easily causes confusion because it resembles OS “permissions”. Always ask: **does this permission belong to the historical JVM policy layer or to OS metadata/enforcement?**

## 9. JDK 17, JDK 24, and the Path Forward

Changes to the Security Manager directly affect reading older code, READMEs, courses, or Java tutorials.

| Timeline | Status to Know |
|---|---|
| Older Java versions | Had Security Manager and policy mechanisms used in some sandbox/plugin environments |
| JDK 17 — JEP 411 | Security Manager and related APIs **deprecated for removal**; do not use for new designs |
| JDK 18–23 | Ongoing transition with per-release changes/warnings; check exact version docs |
| JDK 24 — JEP 486 | **Permanently disable Security Manager**; cannot be enabled at startup or runtime |
| Post-24 JDKs | Per migration guides, native Java Security Manager is not a sandbox solution for modern apps; legacy APIs may remain for transition without historical policy enforcement |

When checking the actual JVM:

```bash
java -version
```

Never build new software requiring `-Djava.security.manager=allow` to isolate plugins and run it on JDK 24+: the mechanism **cannot be enabled**. On JDK 17, remaining flags/configs exist primarily for compatibility/migration, not as long-term architectural advice.

### JEP 411 vs. JEP 486

- **JEP 411 — Deprecate the Security Manager for Removal**: starting in JDK 17, warning and setting the removal direction.
- **JEP 486 — Permanently Disable the Security Manager**: JDK 24 blocks activation; related APIs have degraded behavior to aid transition.

**Permanently disabled does not necessarily mean every API class has already been deleted from bytecode in JDK 24.** Distinguish “disabling the feature” from “removing classes from the JDK”. During migration, check release notes for your exact version.

## 10. What Was `AccessController.doPrivileged` Used For?

In the historical Security Manager architecture, stack-based checks inspected protection domains on the call stack. `AccessController.doPrivileged` executed a code block with special access semantics within Java policy context.

Legacy documentation-style example:

```java
String value = AccessController.doPrivileged(
        (PrivilegedAction<String>) () -> System.getProperty("user.home"));
```

**This is a historical snippet, not recommended for new code.** It requires importing `AccessController` and `PrivilegedAction`, and the JDK 17 compiler may emit deprecation warnings.

Points to distinguish:

- `doPrivileged` does not grant OS file-read permissions to the process.
- It does not escape UID/GID, Windows DACLs, read-only mounts, or container sandboxes.
- From JDK 24 onward, with Security Manager disabled, common `doPrivileged` overloads simply execute the action directly as without a Security Manager, no longer acting as a JVM privilege boundary as originally designed.
- Never wrap a file operation failing with `AccessDeniedException` in `doPrivileged`; that is not how system permissions are fixed.

When encountering legacy code overusing `doPrivileged`, consider **removing the dependency on Security Manager** and designing proper process permissions and business controls instead of merely silencing compiler warnings.

## 11. Absence of `SecurityManager` Does Not Mean the JVM Is Completely Safe or Unsafe

The Java runtime has safety mechanisms other than `SecurityManager`:

- **Type safety, bytecode verification, access modifiers, module boundaries**: protect correctness and limit certain interactions at the language and runtime level.
- **OS permissions, process accounts, filesystem permissions, networking controls**: actually enforce access to system resources.
- **Application authentication and authorization**: decide which user/tenant may perform business actions.
- **Crypto, TLS, key management**: protect confidentiality/integrity and protocol authentication.
- **Process isolation/containers/VMs**: establish stronger boundaries around less-trusted programs.

These mechanisms address **different classes of risk** and do not all replace one another.

A `private` class does not stop the same OS-privileged process from reading a password file if I/O code exists and is invoked improperly. Conversely, protecting a file with mode `600` does not stop the authorized application itself from accidentally logging secrets or returning them to the wrong tenant.

These are two independent verification layers: **business authorization** and **process authority**.

## 12. Choosing a Process Identity Using Least Privilege

Instead of relying on Java policy to restrict individual libraries, run the application with **the minimum operating system privileges needed to do its job**.

Example of a service that only needs to read config files and write logs:

```text
Process identity: app-service

Allowed:
  /etc/my-app/config.yaml       read
  /var/lib/my-app/data/         read/write per business logic
  /var/log/my-app/              append/write per policy
  outbound network              only allowed destinations if egress control exists

Not necessary:
  /root/, other user homes, /etc/shadow
  /var/run/docker.sock
  host device nodes
  broad chown/chmod privileges
```

A production deployment can use:

- A dedicated service user, never running as root/Administrator without a compelling reason.
- POSIX modes + ACLs or Windows DACLs on actual directories/files.
- Containers running as non-root; avoid mounting sensitive host directories or running privileged containers.
- A read-only root filesystem when the app only needs a few writable directories.
- Platform-level network egress/ingress limits, capabilities, and namespaces.
- Secret injection and tight secret-file permissions; never bundle secrets directly in artifacts.
- Audit logs and monitoring for `AccessDeniedException` without printing secret contents.

**A process user inside a container does not automatically mean the same user on the host.** UID mapping, volume mounts, Kubernetes `securityContext`, SELinux/AppArmor, and platform configs must be verified per environment.

### Danger of “Running as Admin to Fix `AccessDenied`”

Elevating privileges for the entire JVM may make the error disappear temporarily, yet it **widens the blast radius** if the app has path traversal, deserialization vulnerabilities, or a compromised dependency. Fix permissions precisely on the required directory, or move file storage to an appropriate location instead of elevating the entire process.

## 13. Complete Java 17+ Example: File Operations and Explaining Permission Boundaries

The following program runs **without `SecurityManager`**. It creates temporary files in an OS-permitted directory, writes and reads with NIO, and illustrates a **purely lexical** path check. The example **does not** attempt to trigger permission errors by altering OS permissions, because results depend on the OS/user/ACL.

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

Compile/run:

```bash
javac OsVsJavaPermissionsDemo.java
java OsVsJavaPermissionsDemo
```

**Exact stdout if the OS allows create/read/write/delete in the temp directory:**

```text
Read: approved-data
Lexically within directory: true
Same normalized target: true
```

Explanation:

1. `Files.createTempDirectory` asks the OS for permission to create a new temporary directory. If the temp dir is not writable, the program can throw `IOException` before printing.
2. `CREATE_NEW` creates a non-existent file, avoiding accidentally truncating an existing `record.txt`. It does not on its own provide a sandbox against path attacks outside the trusted directory.
3. `Files.readString` reads through the provider under the process's real privileges. No Java `FilePermission` is used to “grant” OS permission.
4. `normalize()` removes `reports/..` at the path-string structure level; `startsWith(directory)` returns true for this simple example.
5. **The lexical check above does not prove defense against symlinks/TOCTOU**. It merely shows a preliminary filtering technique; never use `normalize()+startsWith()` alone as a complete security boundary against attacker-controlled paths.
6. All temp resources are deleted in `finally` during normal execution. On sudden kill/crash, `finally` may not run; production apps need another cleanup strategy.

This code is standalone, uses Java 17+, has no admin operations, and omits `SecurityManager` since it is not the platform for building new applications.

## 14. POSIX `FileAttributeView`: Creating Private Files From the Start

When storing secrets on a POSIX-supporting provider, request attributes at **file creation** instead of creating with broad permissions and fixing afterward:

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

This is an **illustrative snippet**, not standalone runnable; the directory must exist, allow creation, and the provider must support POSIX attributes. On Windows filesystems/views lacking support, requesting attributes can throw `UnsupportedOperationException`. Choose appropriate Windows ACL mechanisms rather than catching `IOException` and silently creating a secret file with broad default permissions.

**Benefit:** setting permissions inside the creation call (when supported by the provider) avoids a window where a sensitive file exists with inappropriate permissions before `setPosixFilePermissions` runs.

However, actual read/write access can still be constrained by ACLs/mounts/SELinux, and root/elevated principals may have other privileges. `rw-------` is not a guarantee that “no other user in the world can access it under any mechanism”.

### When the Filesystem Lacks the POSIX View

Do not tie a cross-platform application tightly to `PosixFilePermissions` without checking the environment. You can:

1. Define the file's security requirements.
2. Check view/provider support.
3. If an “owner only” requirement is mandatory yet cannot be configured, **fail closed** instead of creating a sensitive file with uncontrolled permissions.
4. Use OS-appropriate secret storage/ACLs or deploy to an environment with proper isolation.

## 15. `AccessDeniedException`, `SecurityException`, and Other Errors

Java I/O errors that are easily misunderstood:

| Error Type | Typically Indicates | Always Caused by Java `SecurityManager`? |
|---|---|---|
| `AccessDeniedException` | Filesystem/provider reports access to the path is not permitted | No |
| `FileSystemException` | Filesystem problem, may include reason/otherFile | No |
| `NoSuchFileException` | Entry does not exist at operation time | No |
| `FileAlreadyExistsException` | Creating a new entry with an existing name | No |
| `SecurityException` | API/runtime-specific permission/control failure; in older JDKs could come from Security Manager | Do not assume it means OS ACL |
| `UnsupportedOperationException` | Provider/API does not support the requested operation/attribute view | No |
| `IOException` | Broader I/O error category | No |

`Files.*` methods often mention `SecurityException` in historical docs for when a Security Manager is enabled. On JDK 24+, never use the presence of that clause to conclude a Java policy is protecting files. Conversely, when the OS refuses, code typically receives an I/O-type exception; handle per provider and actual context.

**Never write logic like: “Catch `SecurityException` and grant `FilePermission` to make it go away.”** Real permission grants must be resolved through OS/admin configuration or application policy, never silently by unprivileged code.

### Safe Logging

Log useful context: operation, error code, redacted path when necessary, service principal per observability standards, and correlation ID. Never log secret file contents, passwords, or access tokens to diagnose a permission failure.

## 16. Path Traversal Is an Application Bug, Not an OS Permissions Bug

Suppose a web endpoint accepts a filename from the user:

```text
GET /download?file=invoice.pdf
```

If used directly:

```java
Path target = root.resolve(userInput);
byte[] bytes = Files.readAllBytes(target);
```

an attacker can try `../secret.txt` or an equivalent form on the target OS.

If the process **has OS permission** to read that secret file, the OS will not deny it merely because the HTTP caller is unauthorized to view it. The kernel sees **a request from the process account**, unaware of which HTTP user is asking.

The application must enforce:

1. User/request authentication.
2. Authorization by tenant/document ID and business state.
3. Never use arbitrary paths as authority objects; better to map verified IDs to application-managed files.
4. Confine to a fixed root, distinguish files from directories, and prevent symlink escapes.
5. Handle races between check and open, especially in directories writable by attackers.
6. Still run the process under a least-privilege account so the OS blocks most paths outside the service's scope.

### Lexical Checks: Necessary but Not Sufficient

```java
Path base = root.toAbsolutePath().normalize();
Path candidate = base.resolve(userProvidedName).normalize();

if (!candidate.startsWith(base)) {
    throw new IllegalArgumentException("Path outside allowed root");
}
```

This is an illustrative snippet. It blocks some `..` cases after `normalize()`, yet **does not prove the real path stays inside the root** if an attacker can create/swap symlinks or files inside the directory. You must also enforce an absolute-input policy, platform case/volume semantics, and consistent encoding/canonicalization.

If the provider supports `SecureDirectoryStream`, certain operations can run relative to a directory handle to reduce name/symlink swap races. Not every provider supports it; tighter designs typically combine restricted directory permissions, preventing attackers from altering the namespace, file-descriptor/handle checks, and OS isolation. Never call `toRealPath()` once and assume the path stays immutable for all future I/O.

## 17. Temporary Directories, Sensitive Files, and Symlinks

`Files.createTempFile` is a better API than manually building names like `secret-<timestamp>.tmp`, because it creates a new file with a unique name per provider semantics, reducing collisions.

Still, safe design also requires:

- Choosing a **trusted directory** with permissions suited to the service account.
- When creating secret files, applying appropriate permissions/ACLs **right at creation time** if supported by the provider.
- Never using fixed names in world-writable directories without anti-race strategies.
- Not treating `/tmp` as default long-term secret storage; understand sticky bits, cleanup policies, and OS permissions.
- Not passing a temporary path to another process and assuming it cannot alter contents before the file is read back.
- Controlling symlinks/hardlinks and file swaps along paths an attacker can influence.
- Closing file handles and ensuring data is not published prior to validation.
- When important files must be replaced, considering write-temp-then-rename, atomic move where supported, and separate durability requirements.

Note: **atomic rename, file permissions, and application access rights are three independent concerns**. An atomically renamed file can still carry the wrong ACL; a file with the right ACL can still hold wrong business data; an app authenticating users properly still needs filesystem race protection.

## 18. Do Not Rely on a “Java Sandbox” to Run Untrusted Plugins

A common request is “run user-submitted Java code while forbidding it from reading files”. Older Java had an in-JVM sandbox model based on `SecurityManager`. In modern Java:

- Do not use `SecurityManager` as a new security boundary; from JDK 24 it cannot be enabled.
- A single JVM is generally not a suitable security boundary for executing arbitrary code able to invoke powerful APIs.
- `ClassLoader`, module access, Java visibility, and bytecode verification do not provide an equivalent replacement to stop untrusted code from accessing OS resources.
- You need **process/OS-level isolation** with least-privilege accounts, filesystem namespaces/mounts, sandboxes/containers/VMs, network policies, CPU/memory/time quotas, and monitoring.
- For genuinely untrusted code, a container itself does not automatically provide strong isolation if run privileged, mounting the host socket, granting broad capabilities, or disabling security restrictions.
- Never place production secrets in the same filesystem namespace or environment as a process executing untrusted code without an explicit requirement.
- Manage child-process cleanup, timeouts, stdout/stderr, quotas, and prevent child access to runtime/host control sockets.

Programmatic layers restricting “which APIs may be called” remain useful for enforcing **business rules**, yet should never be advertised as a hardened sandbox against an attacker running arbitrary bytecode under the process's OS privileges.

## 19. Application User Authentication/Authorization Is the Third Layer

A server running as user `app-service` may be able to read the entire `/var/lib/app/orders` directory. Yet when Alice calls `GET /orders/123`, whether Alice may view order 123 must be decided by the application:

```text
HTTP request from Alice
   |
   v
Authentication: Who is Alice?
   |
   v
Authorization: Is Alice permitted to view order 123?
   |
   v
Resolve path from domain-validated ID
   |
   v
Filesystem open/read under app-service OS permissions
   |
   v
Response contains only permitted data
```

The OS does not automatically know “order 123 belongs to Alice”. If the application skips authorization, the file read still succeeds because the service process is allowed. This is an **IDOR/broken object-level authorization** bug, unsolvable merely by running `chmod` for a shared service user.

For multi-tenant systems:

- Map tenant + resource ID on the server side.
- Check permissions on every read/write/delete operation.
- Avoid using raw filenames or paths as user-editable object IDs.
- Scope worker/service accounts to the necessary data directories, or isolate per tenant when requirements are strict.
- Audit data access with both the application actor **and** the process/service identity without conflating the two.

## 20. ACLs in Java NIO: How Do They Differ from POSIX Modes?

`AclFileAttributeView` provides a way to work with a list of `AclEntry` objects when supported by the filesystem:

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

This is an illustrative snippet requiring imports for `AclFileAttributeView`, `AclEntry`, `List`, `Files`, `Path`, and `IOException` handling; `path` is assumed declared.

Do not conclude:

- `getAcl()` returning a list means Windows ACLs behave identically to POSIX `rwx`.
- ACE order/type does not affect permission evaluation; ACLs have complex evaluation rules.
- Every provider allows `setAcl`.
- You can use `AclEntryPermission.READ_DATA` to “grant permission” just by instantiating an enum without updating metadata.
- Copying an ACL verbatim from one OS to another preserves semantics.

Modifying ACLs requires understanding principals, allow/deny ACEs, inheritance, and security-descriptor modification rights on the target platform. Never blindly add an `ALLOW ALL` entry to fix file-write failures in production.

## 21. Directory Permissions and Atomic File Updates

Suppose an application writes a configuration file safely:

1. Create a temp file in the destination directory.
2. Write the new data and validate it.
3. Sync the temp file if durability is required.
4. Move the temp file to replace the target name via atomic rename when supported.
5. Verify/preserve appropriate permissions on the new file; clean up temp on error.

The OS may check several distinct capabilities:

- Creating the temp file requires appropriate permissions on the **directory**.
- Writing content requires permission to open/write the **file**.
- Renaming/replacing requires permissions on directory entries and may depend on ACLs/handles.
- Syncing data may be restricted by provider/filesystem.
- Changing owner or ACL on the new file is not automatically allowed for the process.

One notable detail: when creating a **new temp file and replacing the target file**, the owner/ACL metadata of the temp file can become the metadata of the file at the target name. Do not assume atomic replace automatically preserves the old ACL. Set appropriate metadata **before** publishing if the problem requires it.

**Never have Java delete the target file first and then rename the temp file** to “work around permission errors”. That risks losing the old version, creates a gap visible to readers, and still fails if the OS disallows it.

## 22. Difference Between Java Modules/Security and OS Access Control

The Java Platform Module System (`module-info.java`) allows declaring `requires`, `exports`, `opens`, etc. to control code/package accessibility across module boundaries. This **is not** a file-read permission system.

Example:

```java
module com.example.viewer {
    requires java.base;
}
```

This is a `module-info.java` example, not a standalone runnable program. `java.base` is already read by default; the declaration only illustrates syntax.

Do not infer that because a module lacks `requires java.io`, code cannot read the filesystem: `java.io` is a **package** inside `java.base`, not a separate module. Nor should `exports` or `opens` be mistaken for OS permissions. Java module boundaries address encapsulation, readability, and reflective access constraints; I/O permission boundaries require OS/process/application policies.

Similarly, `private`, `protected`, classpath isolation, or package visibility do not establish a filesystem sandbox against code executing inside the same JVM under the same OS principal.

## 23. Comparing Real Errors Using a Diagnostic Table

| Symptom | Possibilities to Check | What Not to Do |
|---|---|---|
| `AccessDeniedException` when reading a file | Process user, ACL/owner, parent dir traverse, mount, sandbox, lock/provider | Construct `new FilePermission` thinking the OS grants access |
| File write denied on Linux | File mode/ACL, dir permissions, read-only mount, SELinux/AppArmor | Immediately run the whole app as root |
| File has `rw-------` yet another process can read it | Actual owner, elevated privileges, namespace, ACLs, shared hardlinks, data already copied | Treat mode bits as encryption |
| `SecurityException` in Java 8/17 code with manager | Java policy/permission check, Security Manager config, classpath | Immediately blame missing `chmod` |
| `System.setSecurityManager` fails in JDK 24+ | JEP 486 permanently disabled the feature | Hunt for a flag to “re-enable” it |
| `Files.isReadable` is true yet reading still fails | TOCTOU, mount/provider, race, sharing/lock, path changed | Treat the probe as authoritative authorization |
| One HTTP user can view another user's file | App authorization / tenant isolation / path traversal | Only tweak Java SecurityManager policy |
| Arbitrary plugin can read secrets | Same process account/namespace, lacking OS isolation | Use only `ClassLoader` as a sandbox |
| POSIX permission API unsupported | Filesystem/provider lacks the view | Skip private-file requirement and publish anyway |
| Container still sees host secrets | Volume mounts, root/capabilities, `securityContext` | Assume “using Docker” is enough |

## 24. Practice: Designing Controlled Experiments

Tests should separate OS behavior from Java mechanisms:

**Exercise 1 — Different process users.** Create a data file in a lab environment and set mode/ACL so only service A can read it. Run **two real processes** under two appropriate accounts/groups and attempt `Files.readString`. Never modify real system files or production secrets.

**Exercise 2 — Directory traverse.** Grant read permission on a file while removing traverse permission on a parent directory in a POSIX test environment, and observe file opening behavior. Restore permissions afterward so you do not lock yourself out.

**Exercise 3 — Probe vs. operation.** Check `Files.isReadable` and then attempt to read; discuss why the two moments can disagree. Do not introduce races by modifying symlinks outside the test directory.

**Exercise 4 — Historical Java policy limits.** Read JDK 17/JEP 411 and JDK 24/JEP 486 documentation; note what role `FilePermission` used to play and why it is no longer used as a sandbox in modern Java. Never enable Security Manager on a live production system just to experiment.

**Exercise 5 — Path traversal.** Write a method resolving filenames inside an application-controlled staging directory. Test `file.txt`, `../file.txt`, absolute paths, and symlinks. Identify what the lexical check filters out vs. why it does not replace symlink-race defense.

**Exercise 6 — Containers.** Run a test service with a read-only root filesystem and one properly permissioned writable volume. List paths needing writes: temp, logs, cache, uploads. Fix errors by adjusting mounts/ACLs intentionally rather than enabling a privileged container.

**Exercise 7 — New secret file verification.** On a suitable POSIX view, create files immediately with owner-only attributes; on Windows, use an equivalent ACL policy. Verify there is no window where the file sits in a shared folder with overly broad default permissions.

## 25. Self-Check Questions

**1.** Without a Security Manager, can `Files.readString` always read any file?  
**No.** The OS/filesystem/mount continues enforcing process permissions.

**2.** Is `new FilePermission(path,"read")` equivalent to `chmod u+r path`?  
**No.** It is merely a Java `Permission` object in the legacy model; it does not alter POSIX modes.

**3.** As of which JDK is `SecurityManager` permanently disabled?  
**JDK 24**, per JEP 486. JDK 17 deprecated it for removal per JEP 411.

**4.** Does `AccessController.doPrivileged` let an unprivileged OS process read `/etc/shadow`?  
**No.** It does not change OS identity/ACLs.

**5.** On POSIX, why might a file with the read bit still fail to open?  
**Possibly** missing traverse permission on a parent directory, other ACL/mount/OS policies, or the process identity does not match that permission.

**6.** Does `Files.isReadable(path) == true` guarantee a file open one second later will succeed?  
**No.** Races/TOCTOU exist and system conditions can change.

**7.** A service process is allowed by the OS to read all tenant files. If the API skips tenant checks, will the OS automatically stop Alice from reading Bob's file?  
**Not according to app tenant logic.** The OS sees the service process; the application must enforce authorization itself.

**8.** Can `ClassLoader` or JPMS replace `SecurityManager` to sandbox untrusted bytecode?  
**Not as a complete OS security boundary.** Proper process/OS/container/VM isolation is required.

**9.** Does a `rw-------` file guarantee nobody can steal data if the app runs as root and logs the entire content?  
**No.** OS mode bits do not protect against an already-privileged application/process or application-layer data leaks.

**10.** When using a temp file and atomic rename to replace a target, is the new file guaranteed to keep the old ACL?  
**No.** The published object is the new file and may carry the temp file's metadata; an explicit permission-preservation policy is needed.

## 26. Safe Java I/O Design Checklist

Before deploying or reviewing a read/write system:

- [ ] Identify the actual **process account** running the JVM.
- [ ] Identify which resources need read, write, create, delete, or rename; grant least privilege.
- [ ] Check **parent directory** permissions, not just files.
- [ ] Understand the filesystem/provider and OS: POSIX modes/ACLs, Windows DACLs, mounts, and sandboxes.
- [ ] Do not rely on `FilePermission` or historical `SecurityManager` to grant/manage OS access.
- [ ] Understand JDK 17 deprecation and JDK 24 permanent disabling of `SecurityManager`.
- [ ] Authenticate and authorize **business users** before mapping IDs to paths.
- [ ] Mitigate path traversal and symlinks; never rely solely on `normalize()+startsWith()` against attackers.
- [ ] Never use `isReadable/isWritable` as a guarantee of success or final security check.
- [ ] Perform real I/O inside `try/catch` and handle `IOException` with context.
- [ ] Create sensitive files with appropriate permissions/ACLs upfront when supported.
- [ ] Isolate namespaces/processes if executing plugins or untrusted code.
- [ ] Never run the JVM as root/Administrator just to avoid ACL configuration.
- [ ] When using containers, verify mounts, user, capabilities, and secret exposure.
- [ ] When publishing temp files, evaluate atomicity, ACL metadata, and durability **independently**.
- [ ] Run real tests on the deployment OS/filesystem instead of inferring from a dev machine.
- [ ] Never log secrets in permission errors or I/O exceptions.
- [ ] Conduct security reviews when changing file permissions, tokens, sandboxes, or service principals.

## 27. Summary

- **OS permissions** are enforced by the kernel/filesystem/access tokens/ACLs/mounts, determining whether a process can access system resources.
- **Historical Java Security Manager** was an in-JVM permission check layer and **never replaced OS permissions**; `FilePermission` merely represented Java policy, not a `chmod`/ACL operation.
- **JDK 17**: Security Manager deprecated for removal (JEP 411). **JDK 24+**: Security Manager permanently disabled (JEP 486); do not build new sandboxes on it.
- **Applications must enforce per-user/tenant authorization themselves**; the OS process account has no awareness of per-request business permissions.
- **`Files.isReadable/isWritable` are probes, not authority**; filesystem races, symlinks, and path traversal require dedicated design defenses.
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