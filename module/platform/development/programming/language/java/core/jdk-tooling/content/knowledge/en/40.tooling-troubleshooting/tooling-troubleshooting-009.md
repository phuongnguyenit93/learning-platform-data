# Missing Permissions in Java Applications

**Missing permissions** occur when a Java process requests to read, write, create, delete, execute, or connect to a resource that the identity running the process is not allowed to use. That resource can be a file, directory, socket, network port, device, another process, database, or API.

An application may run normally on a developer's machine but fail in CI, a service, or a container because the process in those environments runs under a different account. The permissions of the logged-in user are not automatically applied to the JVM, Windows service, Linux daemon, or container.

An effective approach is to identify the denied operation, the target resource, and the process identity; read the exception type along with the reason returned by the operating system; and then grant the exact minimum permissions on that resource. Running the application as Administrator/root or granting permissions to the entire drive often masks the root cause and introduces additional risk.

## 1. Identify which operation is denied

Before changing permissions, describe the specific operation:

| Operation | Typical permissions required |
|---|---|
| Read file | Read permission on the file and traverse permission on parent directories |
| Write existing file | Write permission on the file; may require directory permission depending on the operation |
| Create new file | Write and traverse/search permission on the parent directory |
| Delete file | Write and traverse/search permission on the parent directory; may be subject to sticky bit or ACL |
| Rename/move file | Write and traverse permission on the relevant source/destination directories |
| List directory | Read and traverse permission on the directory |
| Traverse directory | Execute/search permission on the directory |
| Run external program | Execute permission on the file, traverse permission on the path, and a valid interpreter |
| Bind network port | OS port-binding permission, capability, and network policy |
| Connect to service | Network permissions, firewall/egress policy, proxy, and service authentication |
| Read secret/device | ACL, service identity, device permission, or platform policy |

Do not assume that "cannot write file" always means the file itself lacks the write bit. If the application needs to create a new file, the critical permission may be on the parent directory. If it needs to delete a file, write permission on the file itself usually does not determine deletion ability; the system checks permissions on the containing directory and related policies.

Capture the exact absolute path, operation name, timestamp, process ID, and runtime environment. An error message that only says "access denied" without these details is usually insufficient to identify what needs to be fixed.

## 2. Distinguish Java exceptions

Java represents access errors with different exception types depending on the API and file system.

| Exception | Common meaning | What to check |
|---|---|---|
| **AccessDeniedException** | File system denied the operation, usually due to permission or access check | User/group/ACL, parent directory, mount, and service identity |
| **FileSystemException** | File system error with additional file, other file, or reason | Read `getFile()`, `getOtherFile()`, `getReason()` |
| **NoSuchFileException** | File or path component not found | Working directory, path, mount, and file name |
| **FileAlreadyExistsException** | File already exists in an operation requiring creation | Check `CREATE_NEW` and file naming logic |
| **SecurityException** | An API or library rejected an operation according to its security rules | Stack trace, calling API, and platform policy |
| **IOException** | General I/O error; may contain a message provided by the OS/provider | Cause, message, file path, and operating system |
| **AccessControlException** | Historical exception tied to the Java Security Manager | Check legacy code/libraries and JDK version |

`AccessDeniedException` is a checked exception extending `FileSystemException`, and therefore is also a form of `IOException`. NIO typically throws this exception when a file operation is denied.

`SecurityException` is an unchecked exception. Do not automatically conclude that it always means incorrect file system permissions. It can be thrown by an API, library, or application code that performs its own permission checks.

When logging errors, preserve the exception type, message, cause, stack trace, and related path. Avoid logging only `e.getMessage()` and losing information needed for investigation.

Handling example:

```java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadConfig {
    public static void main(String[] args) {
        Path path = Path.of("config", "app.properties");

        try {
            String content = Files.readString(path);
            System.out.println(content);
        } catch (AccessDeniedException e) {
            System.err.println("Access denied: " + e.getFile());
            System.err.println("Reason: " + e.getReason());
        } catch (IOException e) {
            System.err.println("I/O error: " + e.getClass().getSimpleName());
            System.err.println("Message: " + e.getMessage());
            e.printStackTrace(System.err);
        } catch (SecurityException e) {
            System.err.println("Operation rejected: " + e.getMessage());
            e.printStackTrace(System.err);
        }
    }
}
```

This example illustrates how to categorize errors. The file `config/app.properties` must exist and is read using UTF-8 according to the behavior of `Files.readString(Path)`.

## 3. Determine the actual identity of the JVM

Permissions are evaluated against the process performing the operation. Determine which user/group the JVM is running under.

In Java, you can print some basic information:

```java
System.out.println("user.name=" + System.getProperty("user.name"));
System.out.println("user.dir=" + System.getProperty("user.dir"));
System.out.println("java.home=" + System.getProperty("java.home"));
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("os.arch=" + System.getProperty("os.arch"));
```

`user.name` and `user.dir` are useful for diagnostics but do not replace checking the identity at the OS level. `user.name` is a system property and may not fully reflect the effective UID/GID, Windows token, or service identity.

On Linux:

```sh
id
whoami
ps -o pid,user,group,uid,gid,comm -p <PID>
```

On Windows:

```powershell
whoami
whoami /all
Get-Process -Id <PID>
```

In a container, run the `id` command inside the exact container/process namespace. Do not infer it from the host user or from the account that ran the `docker` command.

Common scenarios:

- The developer runs the application under a personal account; CI runs under a runner user.
- A Jenkins agent runs under a service account.
- A Linux service runs under a dedicated user such as `orders`.
- A Windows service runs under a virtual service account or domain service account.
- A container runs under the UID/GID declared in the Dockerfile or runtime.
- A Kubernetes Pod uses `runAsUser`, `runAsGroup`, and `fsGroup`.
- A scheduled task runs under a different account than an interactive login session.

Check the identity in the exact place where the error occurs, not just on the machine where you happen to have a terminal open.

## 4. Check paths and working directory

Relative paths are resolved from the process's working directory. When running in an IDE, terminal, service, or CI, the working directory can differ.

For example, `data/report.txt` may point to:

- `C:\app\data\report.txt` when the process runs from `C:\app`.
- `/opt/orders/data/report.txt` when the service runs from `/opt/orders`.
- `/data/report.txt` when the container has `/` as its working directory.

Print the absolute path to avoid guessing:

```java
import java.nio.file.Path;

Path relative = Path.of("data", "report.txt");
System.out.println("cwd=" + Path.of("").toAbsolutePath());
System.out.println("target=" + relative.toAbsolutePath().normalize());
```

Also check:

- Does the file or directory exist?
- Does the path have the correct letter casing?
- Is there a symbolic link/junction pointing elsewhere?
- Can every parent directory be traversed?
- Is the directory mounted into the container/service?
- Does the path point to a drive, network share, or volume that is mounted read-only?

On Linux, file names are case-sensitive. On many Windows configurations, file names are not case-sensitive in the same way. A path that works on a developer's machine may point to a different file or not exist on the CI system.

Do not create a directory in an arbitrary location just to bypass the error. Confirm the data directory the application is designed to use, then grant permissions at that exact location.

## 5. File and directory permissions on Linux/Unix

POSIX typically represents permissions using three groups:

- `u` — owner.
- `g` — group.
- `o` — others (all remaining users).

Each group has three permissions:

- `r` — read.
- `w` — write.
- `x` — execute for a file, or search/traverse for a directory.

Example:

```text
-rw-r-----  app.properties
drwxr-x---  data/
```

For `app.properties`, the owner can read/write, the group can read, and others have no permissions. For the `data` directory, the owner can read/write/traverse, the group can read/traverse, and others cannot access it.

The `x` permission on a directory means permission to search/traverse through that directory. A process may have read permission on a file and still fail to open it if it lacks search permission on a parent directory.

### Permissions required for each operation

| Operation on directory | Typical permissions required |
|---|---|
| List entry names | `r` |
| Access an entry whose name is known | `x` on the directory |
| Create a new file | `w` and `x` |
| Delete or rename an entry | `w` and `x` on the relevant directory |
| Enter a subdirectory | `x` on each parent directory |

For a file, reading content usually requires `r`; writing content usually requires `w`; executing a file usually requires `x` along with interpreter and mount requirements.

To delete a file, write permission on the file itself is not the primary deciding factor. If the parent directory does not allow write/search, the process still cannot delete the file even if the file has `rw` permissions.

### Check owner, group, and mode

Use:

```sh
id
ls -ld /var/lib/orders
ls -l /var/lib/orders/report.txt
stat -c '%A %a %U:%G %n' /var/lib/orders /var/lib/orders/report.txt
namei -l /var/lib/orders/report.txt
```

`namei -l` displays each path component, helping find a parent directory missing search permission. If this tool is not available, check each directory sequentially from root to the file.

Check ACLs:

```sh
getfacl /var/lib/orders
getfacl /var/lib/orders/report.txt
```

ACLs can grant specific permissions to a user/group beyond the three basic mode groups. The ACL mask can restrict effective permissions even if an entry displays `rwx`; be sure to read the `effective` part in the `getfacl` output.

### Check umask

`umask` affects the default permissions when a process creates a new file/directory. For example, `umask 027` typically gives new files a maximum mode of `640` and new directories a maximum mode of `750`, depending on the mode requested at creation time.

Check in the shell:

```sh
umask
```

`umask` does not modify permissions of existing files. If an existing file cannot be written, check the current owner/group/mode/ACL of the file and directory.

### Fix permissions following the principle of least privilege

If the `orders` service needs to write to its own data directory, an administrator can create the directory with the appropriate owner/group/mode:

```sh
sudo install -d -o orders -g orders -m 0750 /var/lib/orders
```

If a group needs shared write access to a directory, you can use a group and a setgid directory:

```sh
sudo chgrp orders /srv/orders
sudo chmod 2770 /srv/orders
```

Bit `2` (setgid) on a directory causes new files/subdirectories to inherit the parent directory's group on POSIX systems that support this behavior.

If you only need to grant permissions to a single service user via ACL:

```sh
sudo setfacl -m u:orders:rwx /srv/orders
sudo setfacl -d -m u:orders:rwx /srv/orders
```

The second command sets a default ACL for new entries under the directory. Verify again with `getfacl`; effective permissions still depend on the ACL mask and the permissions of each path component.

Do not use `chmod -R 777` as a quick fix. That command grants broad permissions to every user and can expose or allow modification of sensitive data. Grant only the necessary permissions to the right user/group and the right directory.

## 6. Sticky bit, ACLs, and special filesystems

Several cases can be confusing:

- **Sticky bit:** on shared directories like `/tmp`, a user can usually only delete/rename files they own or when they have appropriate administrative privileges.
- **ACL mask:** limits the effective permissions of named user/group ACL entries.
- **Read-only mount:** file mode bits may allow writing, yet the mounted filesystem still rejects writes.
- **Full filesystem or exceeded quota:** may cause `No space left on device` or a quota error instead of a permission error.
- **NFS/root squash:** UID/GID on client and server may map differently; `root` in a container/client does not necessarily have privileges on the server.
- **Network filesystem:** permissions may depend on server ACLs, mount options, and the identity sent over the protocol.

Check mounts:

```sh
findmnt -T /var/lib/orders
df -h /var/lib/orders
df -i /var/lib/orders
```

If mode/ACL permissions look correct but the operation is still denied, check mount options, quotas, network filesystem settings, and host security policies.

## 7. Windows ACLs, UAC, and service accounts

Windows uses Access Control Lists (ACLs) to determine who can access a file/directory and with what rights. Common rights include Read, Write, Modify, Read & Execute, and Full Control.

Check identity:

```powershell
whoami
whoami /all
```

Check the ACL of a directory/file:

```powershell
icacls "C:\AppData\orders"
Get-Acl "C:\AppData\orders" | Format-List
```

`icacls` displays and manages the discretionary ACL (DACL). Inspect the ACEs applied directly and the permissions inherited from parent directories. A `Deny` entry or unexpected inheritance can cause an operation to be denied even when you see an `Allow` entry.

If the administrator confirms the service account needs `Modify` permission on the data directory and its child entries, permissions can be granted for that specific identity:

```powershell
icacls "C:\AppData\orders" /grant "CONTOSO\svc-orders:(OI)(CI)M"
```

In this example, replace `CONTOSO\svc-orders` with the verified service account. `M` stands for Modify; `OI` and `CI` allow permissions to be inherited by files and subdirectories. Apply only when the system administrator approves the ACL scope.

### UAC and Administrator privileges

UAC can run an application with a restricted token even if the user belongs to the Administrators group. A terminal window opened with "Run as administrator" may have a different token than a normal terminal.

Windows services typically run under a dedicated service account. When an application runs as a service, the logged-in user's permissions are not automatically applied to the service process.

Check:

- Which account the service is running under in Services or the service manager configuration.
- Whether that account has permissions on the log, data, temp directories, and configuration files.
- Whether the account has access to certificates/private keys or the secret store.
- If using a network share, whether the account has permissions on both the share ACL and the NTFS ACL.

A mapped drive like `Z:` created in an interactive login session may not exist in the service's session. For network shares, use a UNC path such as `\\fileserver\orders-data` and grant permissions to the exact service identity on both the file server and the share.

### Other Windows causes

An access denied message sometimes comes from:

- The file being held open by another process with an incompatible sharing mode.
- The file or directory having the read-only attribute set.
- Controlled Folder Access or antivirus blocking the operation.
- Group Policy or endpoint protection policies.
- Network share permissions not matching NTFS permissions.
- The service account lacking permission to access a certificate/private key.

Check the event log and security product policies if the ACL is correct yet the operation still fails. Do not disable antivirus or system protection to bypass the error; identify the exact file, process, and policy being blocked.

## 8. Permissions in Docker and containers

Containers have their own filesystem and process identity. A Java process inside a container may run with a different UID/GID than the user on the host.

Check inside the container:

```sh
docker exec <container-name> id
docker exec <container-name> pwd
docker exec <container-name> ls -ld /var/lib/orders
```

A Docker image can choose a default user in the Dockerfile:

```dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /app
RUN mkdir -p /var/lib/orders \
    && chown 10001:10001 /var/lib/orders

COPY app.jar /app/app.jar
USER 10001:10001

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

In this example, the JVM runs as UID/GID `10001`. The data directory is created and owned by that user before switching to the non-privileged user.

When bind-mounting a directory from the host:

```sh
docker run --rm \
  --user 10001:10001 \
  --mount type=bind,src=/srv/orders,dst=/var/lib/orders \
  your-java-image
```

The permissions of `/srv/orders` on the host must allow the mapped UID/GID to access it. Running `chown` on `/var/lib/orders` in the image does not change the owner of the host directory bind-mounted onto it.

Also check:

- Is the container running as the expected `USER`?
- Is the bind mount mounted read-only (`ro`)?
- Does the container UID/GID match the owner/group on the host?
- Is user namespace remapping or rootless Docker enabled?
- Is the host path shared by Docker Desktop?
- Is the volume mounted at the right container path?

`root` inside a container is not always equivalent to `root` on the host. Docker user namespace/rootless mode can map UID/GID to a different ID range; Docker Desktop also uses its own filesystem sharing mechanism. Therefore, running a container as `root` is not a reliable permission fix.

## 9. Kubernetes and volume permissions

In Kubernetes, file access permissions can depend on the Pod/container `securityContext` and the volume type.

Common fields:

- `runAsUser`: UID of the process.
- `runAsGroup`: primary GID of the process.
- `fsGroup`: group used to grant volume access according to the volume driver's behavior.
- `readOnlyRootFilesystem`: makes the container's root filesystem read-only.
- `allowPrivilegeEscalation`: controls whether a process can gain more privileges.
- `securityContext`: security settings at the Pod or container level.

Example:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: orders
spec:
  securityContext:
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
  containers:
    - name: app
      image: example/orders:1.0.0
      securityContext:
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: data
          mountPath: /var/lib/orders
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: orders-data
```

This is an illustrative configuration. Whether `fsGroup` changes volume permissions depends on the volume type and CSI driver. Verify actual permissions inside the Pod using `id`, `stat`, `ls -l`, and test the operation as the exact user.

If the root filesystem is read-only, the application cannot write logs/caches to directories inside the image. Mount a writable volume or configure logs/caches to use the designated writable location.

## 10. Java APIs for checking file permissions

`java.nio.file.Files` provides APIs to check readability/writability/executability:

```java
Path path = Path.of("/var/lib/orders/report.txt");

System.out.println("exists=" + Files.exists(path));
System.out.println("readable=" + Files.isReadable(path));
System.out.println("writable=" + Files.isWritable(path));
System.out.println("executable=" + Files.isExecutable(path));
```

These results are diagnostic only:

- `Files.exists()` can return `false` when the file does not exist or when existence cannot be determined due to missing permissions.
- `Files.isReadable()` and `Files.isWritable()` can return `false` if the file does not exist, permission is denied, or the provider cannot determine it.
- Check results can become stale immediately after returning if permissions, files, or mounts change.
- A successful check does not guarantee that the subsequent open/write will succeed.

This is a TOCTOU (time-of-check to time-of-use) issue: the resource state can change between the check and the operation. In production code, perform the required operation and handle exceptions; use the check APIs as diagnostic aids, not as security guarantees.

You can read the owner or POSIX permissions if the filesystem supports it:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.Set;

Path path = Path.of("/var/lib/orders/report.txt");

try {
    Set<PosixFilePermission> permissions =
            Files.getPosixFilePermissions(path);
    System.out.println(
            "posix.permissions="
                    + PosixFilePermissions.toString(permissions));
    System.out.println("owner=" + Files.getOwner(path));
} catch (UnsupportedOperationException e) {
    System.out.println("POSIX attributes are not supported here");
}
```

Not all filesystems support the POSIX attribute view. On Windows, use the ACL API or OS tools to inspect the corresponding permissions.

## 11. Java 17+ example: probe permissions without overwriting the target file

The program below prints the identity and path, tests opening the file for reading/writing, and then attempts to create and delete a temporary file in the parent directory. It does not write content to the target file.

Create `PermissionProbe.java`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Set;

public class PermissionProbe {
    @FunctionalInterface
    interface IoAction {
        void run() throws IOException;
    }

    private static void check(String label, IoAction action) {
        try {
            action.run();
            System.out.println(label + "=OK");
        } catch (AccessDeniedException e) {
            System.err.println(label + "=DENIED");
            System.err.println("file=" + e.getFile());
            System.err.println("reason=" + e.getReason());
        } catch (IOException e) {
            System.err.println(label + "=IO_ERROR "
                    + e.getClass().getSimpleName());
            System.err.println("message=" + e.getMessage());
        } catch (SecurityException e) {
            System.err.println(label + "=SECURITY_EXCEPTION");
            System.err.println("message=" + e.getMessage());
        }
    }

    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java PermissionProbe <target-file>");
            System.exit(2);
        }

        Path target = Path.of(args[0]).toAbsolutePath().normalize();
        Path parent = target.getParent();

        System.out.println("user.name="
                + System.getProperty("user.name"));
        System.out.println("user.dir="
                + System.getProperty("user.dir"));
        System.out.println("target=" + target);
        System.out.println("exists=" + Files.exists(target));
        System.out.println("readable=" + Files.isReadable(target));
        System.out.println("writable=" + Files.isWritable(target));

        if (Files.exists(target)) {
            check("read-open", () -> {
                try (InputStream input = Files.newInputStream(target)) {
                    input.readNBytes(1);
                }
            });

            check("write-open", () -> {
                try (SeekableByteChannel channel =
                        Files.newByteChannel(
                                target,
                                Set.of(StandardOpenOption.WRITE))) {
                    // Open only; do not write or truncate the target.
                }
            });
        } else {
            System.out.println("read-open=SKIPPED_TARGET_MISSING");
            System.out.println("write-open=SKIPPED_TARGET_MISSING");
        }

        if (parent != null) {
            check("create-delete-in-parent", () -> {
                Path probe = Files.createTempFile(
                        parent, ".permission-probe-", ".tmp");
                Files.delete(probe);
            });
        } else {
            System.out.println("create-delete-in-parent=SKIPPED");
        }
    }
}
```

Compile:

```sh
javac PermissionProbe.java
```

Run with the path to diagnose:

Linux/macOS:

```sh
java PermissionProbe /var/lib/orders/report.txt
```

Windows:

```powershell
java PermissionProbe "C:\AppData\orders\report.txt"
```

Output may look like:

```text
user.name=orders
user.dir=/opt/orders
target=/var/lib/orders/report.txt
exists=true
readable=true
writable=false
read-open=OK
write-open=DENIED
file=/var/lib/orders/report.txt
reason=null
create-delete-in-parent=OK
```

This is illustrative output only; the user name, path, and reason depend on the environment. If `write-open=OK` yet the actual subsequent write still fails, check file locks, quotas, mounts, ACL changes, or errors occurring during write/flush/close.

Running the probe involves creating/deleting a temporary file in the parent directory. Only run it in a directory where you are permitted to test writing. If policy prohibits creating test files, skip that step and use OS tools to check permissions.

## 12. Change POSIX permissions from Java

Java NIO can read or set POSIX permissions when the filesystem supports them and the process has permission to change them.

Example setting owner read/write permissions on a file:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

Path path = Path.of("/var/lib/orders/secret.txt");

Files.setPosixFilePermissions(
        path,
        PosixFilePermissions.fromString("rw-------"));
```

Mode `rw-------` grants read/write permission to the owner and no permissions to group/others. For a directory, traversing usually requires `x`, for example `rwx------`.

`Files.setPosixFilePermissions()` can throw `UnsupportedOperationException` if the filesystem does not support POSIX permissions, and `IOException` if the operation fails. The process usually must be the owner or have appropriate administrative privileges to change permissions.

Do not use application code to arbitrarily elevate file permissions. Permissions should be configured by deployment/provisioning or an administrator under a clear policy. An application should only change permissions when that is a designed and controlled part of its functionality.

## 13. Permissions when running external processes with ProcessBuilder

Java can encounter permission errors when running an executable/script:

```java
import java.io.IOException;

public class RunTool {
    public static void main(String[] args) {
        ProcessBuilder builder =
                new ProcessBuilder("tools/report-generator", "--version");
        builder.inheritIO();

        try {
            int exitCode = builder.start().waitFor();
            System.out.println("exitCode=" + exitCode);
        } catch (IOException e) {
            System.err.println("Cannot start process: " + e.getMessage());
            e.printStackTrace(System.err);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            System.err.println("Interrupted while waiting for process");
        }
    }
}
```

On Linux/Unix, check:

- Does the file have the execute bit set?
- Do the directories along the path have search permission?
- Is the filesystem mounted with `noexec`?
- Does the shebang point to an existing, executable interpreter?
- Does the process have permission to read libraries/configs needed by the executable?

Check with:

```sh
ls -l tools/report-generator
namei -l tools/report-generator
findmnt -T tools/report-generator
```

On Windows, check the executable file, extension, `PATH`, AppLocker/WDAC policy, and process identity. A `CreateProcess` error can be related to a missing executable, wrong path, or policy block, not just file ACLs.

Do not grant execute permission to an entire directory just to run a single script. Grant the necessary permissions to the executable and its containing directories.

## 14. Network permissions and listening ports

Network errors are often confused with file permission errors. Categorize them by exception:

| Exception | What to check |
|---|---|
| `UnknownHostException` | DNS, hostname, resolver |
| `ConnectException` | Service not listening, connection refused, or route/firewall |
| `SocketTimeoutException` | Timeout, firewall/egress, or slow service response |
| `BindException` | Port already in use, restricted by OS/policy, or invalid bind address |
| `SSLHandshakeException` | TLS certificate, trust store, protocol/cipher, and system time |

On Linux, binding to low privileged ports (typically below 1024) may require the `CAP_NET_BIND_SERVICE` capability or system configuration allowing the user to bind that port. A common approach is to have Java listen on a higher port and let a reverse proxy/load balancer accept traffic on the public port.

Check ports:

```sh
ss -ltnp
sudo ss -ltnp
```

On Windows:

```powershell
Get-NetTCPConnection -State Listen
netstat -ano
```

Do not confuse `Address already in use` with `permission denied`. If the error occurs when connecting outbound, check proxy, DNS, firewall, network policy, and service account/network namespace. Do not open all outbound network access if only a specific host/port needs to be allowed.

## 15. Service accounts and systemd on Linux

Services should usually run under a dedicated user with limited privileges. Example systemd unit:

```ini
[Service]
User=orders
Group=orders
WorkingDirectory=/opt/orders
StateDirectory=orders
ExecStart=/usr/bin/java -jar /opt/orders/app.jar
ProtectSystem=strict
PrivateTmp=true
```

`User` and `Group` determine the process identity. `WorkingDirectory` determines relative paths. `StateDirectory` instructs systemd to manage the service's state directory under `/var/lib` with appropriate ownership. `ProtectSystem=strict` makes most of the filesystem read-only to the service, except paths permitted by systemd configuration.

If the service needs to write to another path while using `ProtectSystem=strict`, the administrator can declare `ReadWritePaths=` for that exact directory. Do not remove all hardening just to fix a single file-write error.

After modifying a unit or permissions, reload systemd and restart the service according to operational procedures; an old process may still be running with the previous identity, group membership, or mount namespace.

## 16. SELinux, AppArmor, and host security policies

On Linux, correct mode bits and ACLs may still not be enough. Mandatory Access Control (MAC) such as SELinux or AppArmor can block operations based on security labels/profiles.

Signs:

- `ls -l` shows permissions that look right, yet the process is still denied.
- Only the service/container fails; running in an interactive shell succeeds.
- Kernel/audit logs record an `AVC` denial or `AppArmor DENIED`.
- The file is placed in a path whose label/profile does not allow the service to access it.

Check SELinux:

```sh
getenforce
ls -Z /var/lib/orders
sudo ausearch -m AVC -ts recent
```

Check AppArmor:

```sh
sudo aa-status
journalctl -k
```

If there is a denial, an administrator needs to adjust the label or policy for the specific service and path. Do not disable SELinux/AppArmor system-wide as a default workaround.

In containers, also check seccomp, Linux capabilities, read-only root filesystem, device cgroups, and security profiles. A process may have Unix file mode permissions yet still be blocked by container policy.

## 17. Java Security Manager and newer JDK versions

The Java Security Manager previously allowed restricting certain sensitive operations via a policy file. The lifecycle of this feature has changed:

- JDK 17: Security Manager and related APIs were deprecated for removal.
- JDK 24: Security Manager is permanently disabled; it cannot be enabled via startup options or by installing a custom Security Manager using the legacy mechanism.
- JDK 24 and later: `java.policy`-style policy files are no longer a way to grant file/network permissions to applications.

Therefore, if legacy documentation asks you to add a `grant` permission to `java.policy` or run with `-Djava.security.manager`, check the actual JDK version before applying it. That approach does not solve OS permissions for a service/container and is no longer a supported sandboxing mechanism on modern JDKs.

`SecurityException` remains a valid exception type in Java. It can come from an API or library that implements its own security checks. Do not equate every `SecurityException` with the Security Manager; read the stack trace and specific API documentation.

For resource access control in modern applications, use OS identity, file ACLs, container isolation, network policy, cloud IAM, and application-layer authorization appropriate to each resource type.

## 18. Distinguish OS permissions from application authorization

Not every "forbidden" error comes from the operating system.

Examples:

- **HTTP 403 Forbidden:** the server recognizes the request, but application policy rejects the user/role/tenant.
- **Database permission denied:** the DB account lacks `SELECT`, `INSERT`, `UPDATE`, or schema privileges.
- **Object storage AccessDenied:** IAM policy, bucket policy, service principal, or KMS key policy.
- **Secret manager denial:** the workload identity/role lacks permission to read the secret.
- **File system AccessDeniedException:** the file system provider denied the file operation.
- **Network firewall deny:** the connection is blocked by network policy.

Check the identity in the exact target system. The user running the JVM may be able to read local files while the application's service account still lacks permission to read secrets or object storage.

Do not grant broad OS permissions to fix an application role/tenant error. Fix the policy at the layer that is actually rejecting the request.

## 19. CI/CD and deployment

CI often runs under a different service identity than a developer. Common causes include:

- The workspace or artifact directory has a different owner.
- The runner checks out source into a read-only directory.
- The build cache was created by a different user.
- Deployment keys/certificates are not granted to the job.
- Docker bind mounts have mismatched UID/GID.
- Secret files have modes/ACLs allowing only one account.
- The agent runs with a different network egress policy than local.
- The deployment target or mounted volume is read-only.

In the pipeline, safely log:

- Process user and working directory.
- JDK version, OS, and architecture.
- Absolute path of the failing file.
- Mount/volume and read-only status if applicable.
- Exit code and exception class.
- Name of the service identity/role used, without printing secrets/tokens.

Grant write permissions only to the build output, cache, or deployment staging directories that need them. Source code, build scripts, and executables should keep appropriate read permissions. Do not run CI runners as root/Administrator just so every job can write to every directory.

## 20. Troubleshooting workflow for missing permissions

When encountering an error, follow this order:

1. Identify the denied operation: read, write, create, delete, execute, bind, or connect.
2. Record the exception class, message, cause, stack trace, and involved file/host/port.
3. Print the absolute path and the JVM's working directory.
4. Identify the process user, group, service account, or container UID/GID.
5. Check owner, mode, ACLs, and permissions on every parent directory.
6. Check read-only mounts, filesystem quotas, file locks, and symlinks.
7. Check MAC policies, container security context, or network policies.
8. Test the operation using the exact service/runner identity in the same environment.
9. Grant minimum permissions on the exact resource or fix the identity/configuration.
10. Re-run the operation and verify logs/deployment.
11. Record the new permissions, owner/group, and reason for the change for auditing.

When testing via shell, you must use the exact service user. A command run as `root` or `Administrator` does not prove the service account has permission.

## 21. Common errors and fixes

| Symptom | Common cause | How to check/fix |
|---|---|---|
| Java can read local file, but service cannot | Service runs under a different account | Check service identity and ACL/owner |
| Creating a new file is denied even though directory is readable | Missing write or execute/search on parent directory | Check directory permissions and ACL |
| Reading a file is denied even though file has `r` | Missing `x` on a parent directory or blocked by ACL/MAC | Use `namei -l`, `getfacl`, audit logs |
| Deleting a file is denied even though file has `rw` | Missing write/search on parent directory, sticky bit, or ACL | Check parent directory and sticky bit |
| `Files.isWritable()` returns `true`, yet write still fails | Permission state changed, file lock, or mount/policy | Trust the actual operation result and read the exception |
| Windows runs from terminal, but service fails | Different service account or different UAC/session | Check the service's account and DACL |
| Service cannot access `Z:` drive | Mapped drive does not exist in the service session | Use a UNC path and grant share/NTFS permissions |
| Container cannot write to bind mount | UID/GID mismatch or read-only mount | Check `id`, host owner, mount flags |
| Kubernetes Pod cannot write to volume | `runAsUser`, `fsGroup`, CSI driver, or read-only mount | Check `securityContext` and actual permissions inside the Pod |
| Permissions look right, but Linux still denies | SELinux/AppArmor, `noexec`, or read-only mount | Check audit logs, mount options, and policies |
| Running script via `ProcessBuilder` gets permission denied | Missing execute, parent traverse, shebang, or `noexec` mount | Check file mode, interpreter, and mount |
| Port binding is denied | Low privileged port or capability/network policy | Use a higher port or minimal capability |
| HTTP returns 403 | Application role/tenant policy rejects request | Check principal and authorization policy |
| Database reports permission denied | DB user lacks grant/schema privilege | Check permissions in the database |
| Error occurs only in CI | Runner identity, workspace, cache, secret, or network differs from local | Print environment diagnostics and check service account |
| Permissions were just fixed, but process still errors | Old process, unrefreshed group membership/session, or different mount namespace | Restart the right service/job and re-verify identity |

## 22. Security principles when fixing permissions

- Grant permissions only to the required user/group/service identity.
- Grant permissions only on the required directory/file.
- Prefer groups or specific ACLs for shared environments.
- Do not use `chmod -R 777`, `Full Control` for `Everyone`, or run the application as `root` to bypass errors.
- Keep source code, binaries, and sensitive configs non-writable by the runtime user unless required.
- Separate data, log, cache, temp, and secret directories.
- Use read-only mounts for read-only data.
- Use a secret manager/certificate store instead of writing credentials to public files.
- Record owner/ACL/capability changes in deployment configuration.
- Retest using the exact service identity after making changes.

Overly broad permissions may make an error disappear, but they also allow a compromised process to modify executables, read secrets, or delete data outside its intended scope. Least privilege limits the blast radius if the application or a dependency fails.

## 23. Checklist

- [ ] Identified the denied operation and resource.
- [ ] Read the exception class, message, cause, and stack trace.
- [ ] Identified the actual process user/group or service identity.
- [ ] Printed the working directory and absolute path.
- [ ] Checked every parent directory and symbolic link.
- [ ] Checked owner/group/mode and ACLs.
- [ ] Understood read/write/execute/search permissions by operation type.
- [ ] Checked `umask`, sticky bit, and ACL mask when using POSIX.
- [ ] Checked Windows DACL, UAC, service account, and network share.
- [ ] Checked container UID/GID, volume mounts, and read-only flags.
- [ ] Checked SELinux/AppArmor, `noexec`, and filesystem mounts.
- [ ] Distinguished file permissions from network/application authorization.
- [ ] Tested the operation using the exact process identity.
- [ ] Granted minimum permissions on the exact resource.
- [ ] Re-verified with the actual operation after fixing.
- [ ] Recorded permission changes for auditing.

## 24. References

- Java SE 25 API — AccessDeniedException: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/AccessDeniedException.html
- Java SE 25 API — Files.isReadable, isWritable, and POSIX attributes: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html
- Oracle JDK 27 — The Security Manager Is Permanently Disabled: https://docs.oracle.com/en/java/javase/27/security/security-manager-is-permanently-disabled.html
- Linux man-pages — access(2): https://www.man7.org/linux/man-pages/man2/access.2.html
- Linux man-pages — getfacl(1): https://www.man7.org/linux/man-pages/man1/getfacl.1.html
- Microsoft Learn — icacls: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls
- Docker Docs — Running containers and user identity: https://docs.docker.com/engine/containers/run/
- Docker Docs — Bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- Docker Docs — UID/GID mapping: https://docs.docker.com/engine/security/rootless/uid-gid-mapping/

Missing-permission errors should be resolved at the exact layer denying the operation. Identify the JVM identity, path, and exception first; inspect owner/group/ACL, service account, container mount, or network policy according to the resource type; then grant minimum permissions and retest with the exact process that runs the application.
