# Restricting Log File Permissions in Java: Protecting Log Content, Paths, and Lifecycle

## 1. Objectives

Log files can contain information about processing flows, IP addresses, request IDs, usernames, system errors, stack traces, or business data. If a file is created with overly broad permissions, unauthorized users can still read, modify, delete, or replace logs. **Restricting log file permissions** means applying the *least privilege* principle: only allowing identities and services that genuinely need to read/write/manage logs, with the minimum permissions required for their job.

This lesson belongs to **Logging Security**. The focus is not just running `chmod` on an existing file, but also **permissions at creation time**, the parent directory, the process running Java, post-rotation files, backups, and log collection systems.

After this lesson, you will be able to:
- Understand `owner/group/others` permissions on POSIX and ACLs on Windows, and distinguish file permissions from directory permissions.
- Choose appropriate permission levels for private files (`0600`), group-readable files (`0640`), private directories (`0700`), and group-readable directories (`0750`).
- Configure users/umask at the OS, systemd, or container level; verify permissions after the logger creates and rotates files.
- Create files using Java NIO with POSIX attributes at creation time; handle cases properly when the filesystem does not support POSIX.
- Detect common vulnerabilities: `0777`, `0666`, world-writable directories, symlinks, excessive ACLs, and archive/backup files with widened permissions.

## 2. Threat Model: Who Can Do What with Logs?

Suppose a Java service writes `/var/log/example-app/application.log`:

| Actor | Legitimate Need | Risk If Over-Privileged |
| --- | --- | --- |
| Service account (`exampleapp`) | Create and write application logs | If allowed to write to an uncontrolled shared directory, it can manipulate other files |
| Log collection agent/shipper | Read designated files | If granted write permission, it can alter/delete evidence |
| Operations staff | Read per procedure, troubleshoot incidents | If every account has read access, sensitive data spreads widely |
| Backup/rotation service | Read, move, compress, archive, or create new files | New/backup files may be created with broader permissions than the original file |
| Unrelated accounts | No access needed | Can read, modify, replace, or delete logs if ACL/mode is misconfigured |

**Log security** encompasses confidentiality, integrity, and availability. Mode bits alone do not guarantee tamper-proof logs: the file owner can usually change permissions; an administrator/root or privileged account can access them; deleted files, full disks, or broken pipelines still affect data. For strict auditing, you must add out-of-process storage, tamper-evident mechanisms, and retention policies.

Principles before configuring:
1. Separate service accounts from development/regular login accounts.
2. Grant **write** access only to the service or component that actually manages the file.
3. Grant **read** access only to required shippers/operators.
4. Restrict listing, creating, deleting, and replacing files in the log directory.
5. Evaluate permissions across **all copies** of the logs, not just the current `application.log`.

## 3. POSIX Permissions: Files vs. Directories

On Linux and many POSIX filesystems, permissions have three groups: **owner**, **group**, **others**. `r` = read, `w` = write, `x` = execute/search. Each group has three bits; octal notation and symbolic notation are two ways of representing the same permissions.

| Mode | Representation | Common Meaning |
| --- | --- | --- |
| File `0600` | `rw-------` | Owner read/write only; group and others have no permissions |
| File `0640` | `rw-r-----` | Owner read/write; group read-only; others have no permissions |
| File `0644` | `rw-r--r--` | Other users can read; usually **too broad** if logs contain sensitive data |
| File `0666` | `rw-rw-rw-` | Everyone can read/write; unsuitable for logs requiring protection |
| Directory `0700` | `rwx------` | Only owner can access/list/create according to owner permissions |
| Directory `0750` | `rwxr-x---` | Owner manages; group can list and traverse the directory; others have no permissions |
| Directory `0777` | `rwxrwxrwx` | Multiple accounts can create/delete/rename entries; should not be used for log directories |

The `x` permission on a **file** is execute permission, usually unnecessary for `.log` files. However, `x` on a **directory** allows traversing the path to the file (search/traverse). To read `/var/log/example-app/application.log`, a user needs read permission on the file **and** traverse permission on all relevant parent directories. The `r` permission on a directory allows listing filenames, without automatically granting read access to individual file contents.

Specifically, **deleting/renaming a file** is usually governed by write + traverse permissions on the **parent directory**, not just the `w` bit on the file itself. Therefore, a `0600` file placed inside a `0777` directory is still at risk of being replaced/deleted by anyone with directory permissions (depending on the sticky bit and ACLs). Never inspect just one file and conclude the entire path is secure.

`0600` and `0640` are only policy examples. When a shipper needs to read logs, `0640` with a restricted group/ACL may be more appropriate than `0600`. **Do not grant `others` permissions just to make a shipper work**.

## 4. Permissions Are Decided at File Creation Time

A new log file can be created when the service starts, when Logback/Log4j/JUL opens the file target, or after a rollover. You must distinguish:
- **Process identity:** UID/GID or Windows service identity of the Java process.
- **Default creation permissions:** determined by the application, library, filesystem, and OS policy.
- **Umask on POSIX:** a mask that strips permission bits when creating files/directories via standard mechanisms.
- **Default ACLs, inherited groups, mounts/volumes:** can affect owner/group, effective permissions, or access behavior.

As a typical example on POSIX, if an application requests file creation mode `0666`:
- `umask 0077` strips group/others permissions, typically yielding a new file with `0600`.
- `umask 0027` typically yields a new file with `0640`.
- For directories requesting `0777`, the two umasks above typically create `0700` and `0750` respectively.

This is the **common calculation**, not a guarantee that every logging backend requests exactly `0666` or that the filesystem has no ACLs. `umask` alone does not fix permissions on existing files, does not guarantee backups/rotations always use the same mode as the original file, and does not replace post-creation verification.

**Avoid the "create a public file then chmod it to private" workflow**: if a file is readable by others at creation time, a data exposure window can occur before `chmod` runs. It is better to assign the right mode at creation time or create it inside a service-only directory, then verify.

## 5. Setting Up Directories and Users on Linux

Suppose a service is named `exampleapp`, has a dedicated OS account of the same name, and only the service should read/write logs.

An example of controlled directory preparation (executed by an administrator, **not a command the application runs itself**):

```bash
sudo install -d -o exampleapp -g exampleapp -m 0700 /var/log/example-app
sudo ls -ld /var/log/example-app
```

Purpose:
- `install -d` creates/configures the log directory owned by the service account.
- `0700` prevents other accounts from listing or traversing the directory via mode bits.
- Do not run the application as `root` just because it lacks log write permissions; fix the owner/permissions on the proper directory or use a dedicated directory provisioned by the service manager.

Example POSIX-style display when setup succeeds (owner/group names depend on the machine):

```text
drwx------ ... exampleapp exampleapp ... /var/log/example-app
```

The `...` placeholders represent time/system-dependent `ls` fields, **not fixed stdout**.

If a **log collection agent** needs read access:
- Add the agent to a group allowed to read, or grant a read-only ACL to the specific service principal.
- Files need group read permission (typically `0640`) and directories need group traverse permission (typically `0750`).
- Configure the owning group for new files properly; on POSIX, you can use the process group, setgid on the directory, or a default ACL depending on policy.
- The agent does not need write permission on files or directories unless a task genuinely requires it.

Avoid `chmod -R 777 /var/log/example-app` or `chmod -R 666` as a "quick fix for permission errors": it over-exposes permissions, can create log reading/deletion vulnerabilities, and does not solve the underlying owner/group issue.

### 5.1. systemd: Granting Permissions at Log Creation

For an application running as a **systemd system service**, you can use a unit configuration:

```ini
[Service]
User=exampleapp
Group=exampleapp
UMask=0077
LogsDirectory=example-app
LogsDirectoryMode=0700
ExecStart=/usr/bin/java -jar /opt/example-app/app.jar
```

This is an **illustrative configuration snippet**, requiring the actual account, JAR, and paths to exist. Under systemd's `LogsDirectory` mechanism, a system service creates the appropriate directory under `/var/log/` with the service's owner/group; `LogsDirectoryMode` governs the directory's mode. `UMask=0077` restricts file creation permissions for the process and its child processes according to umask rules.

Two important points:
1. `UMask` **does not retroactively** chmod existing files or files created by an independent process that does not inherit that umask.
2. Rotation performed by `logrotate`, backends, or other agents may have separate owner/group/mode configurations; you must inspect files after rollover.

Do not directly edit the unit of a running service without a proper change/restart procedure. For containers/Kubernetes or other service managers, apply equivalent policies at the appropriate layer.

## 6. Java NIO: Creating Files with POSIX Permissions at Creation Time

Java NIO provides `Files.createFile(Path, FileAttribute<?>...)`, `Files.createTempDirectory(...)`, `PosixFilePermissions`, and `Files.getPosixFilePermissions`. When the filesystem supports the POSIX attribute view, you can request permissions directly in the file/directory creation operation:

```java
Set<PosixFilePermission> perms =
        PosixFilePermissions.fromString("rw-------");
Files.createFile(path,
        PosixFilePermissions.asFileAttribute(perms));
```

The attributes are passed **in the same creation operation**, reducing the window where a new file is created with broad default permissions before being fixed. According to the Java API, actual permissions may be **equal to or stricter than** requested due to umask/filesystem policy. Re-verify after creation; do not assume the method yielded the exact bits.

### 6.1. Standalone Java 17+ Example: Checking POSIX Support and Creating a Private File

The program below uses the system temporary directory for demonstration and does not write to production paths. On systems that do not support the POSIX attribute view (typically NTFS/Windows), it **does not emulate Unix chmod** and instead reports that OS-specific ACLs must be configured.

Create **`SecureLogPermissionsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

public final class SecureLogPermissionsDemo {
    public static void main(String[] args) throws Exception {
        Path base = Path.of(System.getProperty("java.io.tmpdir"));

        Set<PosixFilePermission> privateDir =
                PosixFilePermissions.fromString("rwx------");
        Set<PosixFilePermission> privateLog =
                PosixFilePermissions.fromString("rw-------");

        System.out.println("requested-file-mode="
                + PosixFilePermissions.toString(privateLog));

        if (!Files.getFileStore(base)
                .supportsFileAttributeView("posix")) {
            System.out.println("POSIX_NOT_SUPPORTED");
            return;
        }

        Path dir = Files.createTempDirectory(
                base, "safe-logs-",
                PosixFilePermissions.asFileAttribute(privateDir));
        Path log = dir.resolve("application.log");

        try {
            // CREATE_NEW: fails if already exists, including symbolic links.
            Files.createFile(log,
                    PosixFilePermissions.asFileAttribute(privateLog));
            Files.writeString(log, "event=demo\n",
                    StandardCharsets.UTF_8, StandardOpenOption.APPEND);

            System.out.println("directory-mode="
                    + PosixFilePermissions.toString(
                            Files.getPosixFilePermissions(dir)));
            System.out.println("file-mode="
                    + PosixFilePermissions.toString(
                            Files.getPosixFilePermissions(log)));
        } finally {
            Files.deleteIfExists(log);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run on JDK 17 or later:

```bash
javac SecureLogPermissionsDemo.java
java SecureLogPermissionsDemo
```

**When the filesystem does not support POSIX**, the deterministic output is:

```text
requested-file-mode=rw-------
POSIX_NOT_SUPPORTED
```

**When the filesystem supports POSIX** and the mode is fully applied, a common output is:

```text
requested-file-mode=rw-------
directory-mode=rwx------
file-mode=rw-------
```

Actual POSIX results may be **stricter** due to umask or filesystem rules. If the process lacks create/write permissions in the temp directory, the program may throw an exception—that is an environment permission error, not a reason to loosen permissions for everyone. The example deletes the files it creates after running successfully.

How it works:
1. `PosixFilePermissions.fromString(...)` represents permissions as a `Set<PosixFilePermission>`.
2. `Files.getFileStore(base).supportsFileAttributeView("posix")` checks for support before using POSIX attributes. Do not infer support solely from the OS name.
3. `Files.createTempDirectory(..., attrs)` and `Files.createFile(..., attrs)` request permissions at creation time.
4. `Files.writeString(..., APPEND)` writes a line to the service-owned file; this is a demonstration operation, not a Logback appender.
5. `Files.getPosixFilePermissions` reads back the mode, and `finally` cleans up the file and directory created by the example.

**Example limitations:** this demonstrates the secure file creation mechanism, not an automated file appender configuration process. A real logger may **create or recreate** files using its own API. If pre-creating files, you must verify that the appender opens that exact file and that post-rotation paths remain protected.

### 6.2. Why Calling `setPosixFilePermissions` After Creation Is Not Enough

`Files.setPosixFilePermissions(path, perms)` modifies the mode of an **existing** file and is useful when fixing configurations. However, when using:

```java
Files.createFile(path);
Files.setPosixFilePermissions(path,
        PosixFilePermissions.fromString("rw-------"));
```

these are two separate operations. In between, the file may carry default permissions broader than required (depending on umask/ACL). For sensitive files, use `FileAttribute` at creation time or create them inside a pre-provisioned secure directory.

Also do not use `java.io.File#setReadable(...)`/`setWritable(...)` assuming they produce the same standard ACL outcome across all OSes. Those convenience APIs may not fully express Windows ACLs, default ACLs, owner/group, and volume security policies.

## 7. Java NIO on Windows: ACLs Instead of Unix chmod

Windows with NTFS typically uses **Discretionary Access Control Lists (DACLs)**. Permissions are assigned to *security principals* such as:
- A dedicated Windows service account or service SID.
- `SYSTEM`, `Administrators`.
- Explicitly designated log collection groups/agents.
- Default groups with inherited permissions from parent directories (must be inspected).

You cannot apply `chmod 600` to NTFS and consider it fully secured. Java NIO provides `AclFileAttributeView`, `AclEntry`, and `UserPrincipal` to read/set ACLs on supported providers; proper implementation depends on service identity, inherited entries, and required rights. On Windows, prefer **provisioning log directory permissions at provision/deploy time** via OS tools/IT workflows rather than having the application try to rewrite entire ACLs on startup.

**Read-only** commands for inspection:

```powershell
icacls "C:\ProgramData\ExampleApp\logs"
Get-Acl -Path "C:\ProgramData\ExampleApp\logs" |
    Format-List Owner,AccessToString
```

Replace the path with your actual log directory. These commands do not modify ACLs themselves.

When designing a DACL, one model is:
- Service: create/write/read permissions suitable for running the appender and rotation, scoped only to its log directory.
- Shipper: **read/traverse** if only collection is needed.
- System administrators: management permissions per policy.
- Unrelated Users/Everyone/Authenticated Users: do not grant read/write permissions to logs containing sensitive data.
- Verify **inherited ACEs** from parent directories and **effective access**; adding a single Deny/Allow entry without reviewing the full DACL can widen permissions or lock out the service.

Do not blindly copy an `icacls /inheritance:r` command across machines: changing inheritance can strip necessary administrator/SYSTEM permissions. Test on a provisioned directory in a staging environment and verify against the real service account.

## 8. Logging Frameworks: Who Creates the File and Who Controls the Mode?

Crucial condition: **whichever component creates the file**—along with its runtime environment—is responsible for the initial permissions.

### 8.1. Log4j 2 Core

Per Log4j 2 documentation, `File` and `RollingFile` appenders support the `filePermissions` (POSIX) attribute, along with `fileOwner`/`fileGroup` when supported by the filesystem and OS privileges. Example **XML configuration snippet**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="PRIVATE_FILE"
                     fileName="/var/log/example-app/application.log"
                     filePattern="/var/log/example-app/archive-%d{yyyy-MM-dd}-%i.log.gz"
                     filePermissions="rw-------">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <SizeBasedTriggeringPolicy size="10 MB"/>
            </Policies>
        </RollingFile>
    </Appenders>
    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="PRIVATE_FILE"/>
        </Root>
    </Loggers>
</Configuration>
```

This snippet requires the application to run a Log4j 2 Core version that supports these attributes, with a provisioned directory where the service has write permission. `filePermissions="rw-------"` specifies the desired permissions for files created by the appender on POSIX; it does not make NTFS support POSIX, nor does it replace owner configuration, umask, or directory security.

**Inspect files after rollover**: archive names may differ, and compression/moving processes have their own permissions. Log4j 2 also has a `PosixViewAttribute` rollover action to conditionally change permissions on archived files; configure it only when genuinely needed and verify the version, path scope, and `followLinks`. Never assume archived/compressed copies retain all metadata of the active file.

### 8.2. Logback and JUL

With **Logback** (`FileAppender`/`RollingFileAppender`) or JUL `FileHandler`, effective permissions depend on the file creation mechanism, process user/group, umask, and directory/volume permissions. Do not assume Logback XML understands `filePermissions` just because Log4j 2 has an attribute by that name.

When using Logback/JUL:
1. Provision a dedicated log directory and restrict permissions before the appender runs.
2. Run the JVM under a least-privilege service account; configure appropriate umask/ACLs via the service manager.
3. Inspect the actual **newly created file**, not just an old file that was previously `chmod`ded.
4. Test rollover, restart, compression, and backup; verify owner/group/mode/ACL on each file type.
5. If a collector reads the files, grant dedicated permissions to the collector rather than switching the appender to run as root.

In applications using SLF4J, remember that SLF4J is an API; the underlying provider (Logback, Log4j, JUL bridge, etc.) determines where and how files are created. Read the documentation for your specific backend and deployed version.

## 9. Rotation and Archival Are Part of Log File Permissions

Log files rarely exist in isolation: there is the active file, old files, compressed files, backup copies, files read by shippers, and objects in collectors. Each step can **create a new inode/file** with different modes/ACLs.

Scenarios to verify:
- **Restart:** does the appender reopen the existing file or create a new one? How do owner and mode change?
- **RollingFile/rolling policy:** are archive files moved or copied/compressed, and does that create a publicly readable new file?
- **logrotate on Linux:** if using `create`, the new file's owner/group/mode follows logrotate's config. Does the service actually reopen the new file?
- **Compression:** do `.gz` files receive restricted permissions and reside in a secure directory?
- **Backup/restore:** are ACLs/modes preserved or reapplied at the restore destination?
- **Retention:** are files deleted on schedule, without leaving old copies indefinitely in buckets, temp directories, or CI artifacts?

An illustrative **logrotate** configuration snippet when using standalone logrotate:

```text
/var/log/example-app/application.log {
    daily
    rotate 7
    missingok
    notifempty
    create 0600 exampleapp exampleapp
}
```

The `create 0600 exampleapp exampleapp` directive instructs logrotate to create the new file with the specified mode/owner/group. **Do not apply this configuration blindly** if the logging backend also performs its own rolling: the two mechanisms can contend over the same path. After logrotate moves the current file, the JVM may keep writing to the old file descriptor until the appender is reopened; a proper reopen/restart procedure is required. Archive/backup permissions must also be verified separately.

Avoid treating `copytruncate` as a risk-free solution: while copying and truncating, log entries written during the race window can be lost. Choosing a rotation strategy involves data integrity, not just permissions.

## 10. Untrusted Directories, Symlinks, and Path Traversal

Suppose a log file has mode `0600`, but a parent path grants write access to an untrusted account. An attacker could attempt to:
- Create a symlink at the expected filename to trick the logger into opening a different target.
- Delete/rename the entry and replace the file, tampering with the data source.
- Manipulate filenames or path segments from input, redirecting logs outside the intended directory.

**Log paths should be fixed and located under a service/admin-controlled directory**, never constructed by concatenating filenames from external HTTP/request data. Do not grant unrelated users write access to the log directory.

Technical notes:
- `Files.createFile(path, attrs)` uses a create-new operation; if the target path already exists—including as a symlink—it will not simply overwrite that target's contents.
- Checking `Files.isSymbolicLink(path)` and then opening the file in a separate operation **is not absolute protection** because a race condition can occur between check and open.
- `LinkOption.NOFOLLOW_LINKS` and `StandardOpenOption.CREATE_NEW` are useful in supporting APIs, but they do not replace protecting parent directories, mounts, and the identity opening the file.
- Never automatically `chmod`/`chown` a path derived from untrusted input; changing permissions on the wrong target can be a severe vulnerability.

If multiple applications share a directory, separate them into per-service subdirectories with independent permissions. A single world-readable log file in a broadly accessible directory undermines all redaction efforts.

## 11. Containers, Kubernetes, stdout, and Collectors

Many containerized Java applications write logs to **stdout/stderr** instead of opening `/var/log/...` themselves. In that case:
- Files on the host are created/managed by the container runtime, log driver, kubelet, or collector.
- Running `chmod` or `Files.setPosixFilePermissions` inside the JVM **does not** change permissions of runtime-created log files on the host.
- You must inspect user/container security contexts, volume mounts, host paths, log drivers, runtimes, and access controls in the centralized logging system.

If the appender writes directly to a mounted volume:
- Determine the effective UID/GID inside the container and the actual owner/group of the volume.
- Verify that the volume directory allows the service to write while restricting others.
- Do not assume `runAsUser` or `fsGroup` turns every storage provider into the same permission model; verify deployment behavior.
- Ensure init jobs/sidecars/backups do not recreate files with broad modes/ACLs.

If using **journald**, a collection system, or cloud logging, you must enforce reader permissions at the **journal/collector** level and via IAM/retention policies, not just local file modes. The same event can exist in multiple places: application files, stdout, journal, agent buffers, collectors, object storage, and exported reports.

## 12. Verifying Effective Permissions: Don't Just Read Configs

On Linux, commonly used read-only commands:

```bash
ls -ld /var/log/example-app
ls -l /var/log/example-app/application.log
stat -c '%a %U:%G %n' /var/log/example-app/application.log
namei -l /var/log/example-app/application.log
getfacl -p /var/log/example-app/application.log
```

`stat -c` and `namei` use syntax common on GNU/Linux systems; `getfacl` may require the ACL package. Output varies by system; do not expect fixed output. `namei -l` reveals permissions on every directory in the path, while `getfacl` inspects ACL entries beyond simple mode bits.

Verify **on newly created files**:
1. Start the appender under the proper service identity.
2. Emit a test event containing no sensitive data to ensure the file is created.
3. Read owner/group/mode/ACL and confirm an out-of-scope account genuinely **cannot read** it.
4. Trigger a rollover in a test environment, inspecting the active file, archives, and compressed files.
5. Log out/restart and re-verify to catch configs that only appeared to work on old files.

On Windows, use `icacls` and `Get-Acl` from Section 7, then verify effective rights of the service SID/agent. Administrative tools may be needed to simulate other accounts; do not conclude a DACL is secure just because an admin account can read it (admins are inherently privileged).

### Minimum Verification Matrix

| Scenario | Expectation for Private Log Files |
| --- | --- |
| Service writing logs | Can open/append and roll over properly |
| Unrelated user reading file | Denied per policy |
| Unrelated user modifying/deleting file | Denied via both file and parent directory |
| Designated shipper | Can read, typically does not need modify/delete |
| New file after restart | Permissions no broader than policy |
| Archive file after rotation | Equivalently protected |
| Compressed/backup/restored files | Do not land in public buckets/directories |
| Windows/non-POSIX volumes | Use appropriate ACLs/providers, do not pretend chmod succeeded |

## 13. Separating File Permissions from Log Content Security

**Restricting log file permissions is a necessary defense layer, but not sufficient on its own.** Even a `0600` file can still contain tokens or personal data readable by the service, admins, or backups. Secure logging rules:
- Do not log passwords, API keys, bearer tokens, session cookies, card numbers, or unnecessary sensitive data.
- Limit stack traces/payloads when secrets might leak; prefer business IDs and controlled error details.
- Redact/mask at the source whenever possible, alongside enforcing retention.
- Separate mandatory audit logs from debug logs if integrity or forensic investigation is required.
- Encrypt at rest/in transit when required, protect encryption keys separately, and control IAM for collectors and backups.
- Monitor permission/ACL changes and reads of sensitive logs when security requirements dictate.

Any account with write access to a log file can alter its contents; `chmod 600` **does not** make logs tamper-proof against the owner or administrator. For critical audit trails, consider append-only/tamper-evident pipelines, off-host storage, and record verification.

## 14. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| `chmod 777` on log directory for "easy writing" | Anyone can create/delete/rename entries | Dedicated service account, `0700`/`0750` directory |
| `0600` file inside a directory writable by outsiders | Entries can be replaced/deleted via the directory | Lock down directory and parent path permissions |
| Running `chmod` after the file already holds logs | Leaves a window with overly broad default permissions | Set at creation time, pre-configure umask/ACLs |
| Fixing permissions only on the current file | Restarts/rotations create files with different modes | Test new files and archives after rollover |
| Running Java as root to fix `Permission denied` | Elevates privileges for the entire application | Fix owner/group/ACL in the right place |
| Checking only `ls -l`, ignoring ACLs and parent paths | ACLs/dir traversal may differ | Use `namei`, `getfacl`, check effective access |
| Using `setPosixFilePermissions` on Windows | Provider does not support POSIX | Use Windows ACLs/`AclFileAttributeView` |
| Granting shippers write/delete permissions | Can tamper with or destroy evidence | Grant read/traverse only when sufficient |
| Using both logrotate and RollingFile uncoordinated | Unexpected file descriptors, permissions, or rotation | Choose a clear strategy and test reopen |
| Logging to stdout then `chmod`ding files in container | Files are managed on the host by the runtime | Check runtime/host log policies |
| Logging sensitive data because "it's chmod 600" | Owner/admin/backup can still read it | Minimize, redact, encrypt, enforce retention |
| Using filenames from requests | Enables path traversal or arbitrary file creation | Use predefined paths, reject untrusted path input |

## 15. Hands-On Exercises

1. On a test Linux machine, create a private directory with `0700` and a file with `0600`. Use `ls -l`/`stat` to verify; test with another account to understand file vs. parent directory permissions.
2. Create a `0750` directory with a shipper group and a `0640` file. Verify the shipper can only read and cannot modify or delete the file.
3. Run `SecureLogPermissionsDemo` on a POSIX filesystem. Explain `requested-file-mode`, `directory-mode`, and `file-mode`; if results are stricter, relate them to umask and filesystem policy.
4. Run the program on Windows/NTFS. Why does it output `POSIX_NOT_SUPPORTED`? Use `icacls` to inspect the ACEs of a test directory instead of trying to run Unix chmod.
5. Configure a Log4j 2 `RollingFile` appender with `filePermissions="rw-------"` on test Linux; inspect the active file and archives after rollover.
6. If using Logback/JUL, create a new file under a service account configured with `UMask=0077`; inspect the actual mode after a restart, not just the old file.
7. Simulate logrotate in a test environment and confirm the appender still writes to the right file after rotation; check modes on both the active log and compressed files.
8. Compare a container logging to stdout versus a container writing to a mounted volume: who creates the file, who has read access, and at which layer does the policy live?

## 16. Key Takeaways

- **Protecting log files starts with the user/process, parent directory, and creation-time permissions**, not just running `chmod` after an incident.
- On POSIX, `0600` for files and `0700` for directories are strong starting points for private logs; `0640`/`0750` fit when a group needs read access.
- Java NIO supports `PosixFilePermissions.asFileAttribute(...)` at creation time; check the provider and read back actual permissions. Windows uses ACLs.
- Rolled-over files, compressed archives, backups, container host logs, and collectors are **separate copies that must be controlled individually**.
- Never use broad permissions or run as root to mask configuration errors. File permissions do not replace redaction, retention, encryption, or reliable auditing.

### References

- Oracle Java 17 — `Files.createFile`, `Files.createTempDirectory`, and file attributes: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Oracle Java 17 — `PosixFileAttributeView` and initial permissions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html
- Oracle Java 17 — `PosixFilePermissions`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- Oracle Java 17 — `AclFileAttributeView`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html
- Apache Log4j 2 — FileAppender permissions: https://logging.apache.org/log4j/2.x/manual/appenders/file.html
- Apache Log4j 2 — RollingFileAppender and `PosixViewAttribute`: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- systemd — `UMask`, `LogsDirectory`, and `LogsDirectoryMode`: https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
- Microsoft — `icacls`: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls