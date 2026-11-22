# Permissions and OS Support for File Links (Java NIO.2)

File links allow multiple paths to reference the same data or allow one path to redirect to another path. In Java, the `java.nio.file.Files` API supports **symbolic links** (soft links) and **hard links**, but whether an operation succeeds depends on **the operating system, the file system, process permissions, and runtime security policies**. Compiling successfully on Java 17+ does not guarantee that every link type can be created on every machine.

## 1. Understanding What Permissions Apply To

| Criterion | Symbolic link (symlink) | Hard link |
| --- | --- | --- |
| Mechanism | A file system entry storing **a target path**; the OS resolves the target upon access. | Another name/directory entry pointing to **an existing file object** (typically sharing the same file identifier). |
| Target at creation | May not exist yet: creates a *dangling symlink*. | Existing object must already exist; typically a regular file, not a directory. |
| Effect when renaming/deleting original path | The link can break if the path stored in the link is no longer valid. | Another hard link can still access the data even if the original name is deleted, as long as one link/file is still held by the system. |
| Different file system | Can contain a path pointing elsewhere; access succeeds only if the target is reachable. | Usually required to be on the same file system/volume. |
| Access permissions | Permissions when opening content apply according to the actual target and directories along the path. | Names share the same object, so permissions on the file object are usually shared; permission to rename/delete directory entries still depends on the parent directory. |
| Java API | `Files.createSymbolicLink(link, target)` | `Files.createLink(link, existing)` |

For example, `/data/report.txt` is a real file; `/work/report-link.txt` can be a symlink storing `/data/report.txt`; and `/data/report-copy-name.txt` is a hard link to the exact same file object as `/data/report.txt`. **A hard link does not copy bytes.** What Windows calls a "shortcut" (`.lnk`) is a Shell file format and **differs** from a file system symbolic link: `Files.createSymbolicLink` does not create `.lnk` files.

A **path** (`Path`) is a name used to locate; a **file object** is the resource managed by the file system. Distinguishing these two helps explain link deletion, access permissions, and content modifications.

## 2. Essential Java APIs and Link-Following Rules

| API | Meaning and Key Points |
| --- | --- |
| `Files.createSymbolicLink(link, target)` | Creates a symlink; `target` can be a relative or absolute path. This is an *optional* operation depending on provider and permissions. |
| `Files.createLink(link, existing)` | Creates a hard link to an existing file; may be rejected due to different file stores or system policy. |
| `Files.isSymbolicLink(path)` | Checks whether the `path` entry itself is a symlink; does not need to open target content. |
| `Files.readSymbolicLink(path)` | Retrieves **the path stored** inside the symlink; does not automatically convert to absolute or verify target existence. |
| `Files.exists(path)` | Follows symlinks by default; if the target does not exist, can return `false`. Also returns `false` when existence cannot be determined. |
| `Files.exists(path, LinkOption.NOFOLLOW_LINKS)` | Checks the link entry itself, even if its target is broken. |
| `Files.readAttributes(path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS)` | Inspects metadata of the link rather than the target object. |
| `path.toRealPath()` | Returns the real path after resolving links (by default), requiring the path to exist. `toRealPath(NOFOLLOW_LINKS)` applies the no-follow policy. |
| `Files.isSameFile(a, b)` | Compares whether two paths identify the same file, may throw `IOException`; useful for verifying hard links. |
| `Files.delete(path)` | If `path` is a symlink, deletes **the symlink entry**, not the target file. If deleting a hard link, removes one name of the file. |
| `Files.walkFileTree(root, visitor)` | By default **does not** follow symlinks to directories. Enable `FileVisitOption.FOLLOW_LINKS` only when truly needed and handle cycles. |

For a relative symlink, `target` is interpreted **relative to the directory containing the link**, not Java's working directory. For example, creating `/app/links/log` pointing to `../logs/current.log` resolves to `/app/logs/current.log`. If the link itself is moved to another directory, the meaning of the relative target can change. `Path.normalize()` only normalizes `.`/`..` syntax; it **does not** open links to confirm the real target.

Several easily overlooked differences:

- `Files.readString(link)` and many content-reading operations normally follow symlinks; however, APIs with a `LinkOption` parameter allow choosing different behavior.
- `Files.copy(sourceLink, target)` by default copies **the target content** of the source symlink; `Files.copy(sourceLink, target, LinkOption.NOFOLLOW_LINKS)` requests copying the link itself when supported. Do not assume all copy/move operations dereference the same way.
- `Files.move(sourceLink, dest)` moves the source symlink entry, without rewriting the path stored in the link to a "new" target for you; re-verify relative links after moving.
- `Files.walk` or `walkFileTree` when `FOLLOW_LINKS` is enabled may encounter cycles; `FileSystemLoopException` or related I/O errors must be handled. For user-provided data trees, not following links by default is usually safer.

## 3. Permission Conditions: Creating a Link vs. Accessing the Target File

When using `Files.createSymbolicLink(link, target)` or `Files.createLink(link, existing)`, separate three questions:

1. **Do you have permission to create a new entry in the directory containing `link`?** On Unix/POSIX, this usually requires write (`w`) and execute/traverse (`x`) permissions on the parent directory; ACLs, sticky bit, mount options, or security policies can also affect it. On Windows, this relates to directory ACLs/permissions and the process token.
2. **Do you have permission to create that link type?** Symlinks/hard links have their own OS, driver, and file store constraints. For example, Windows has a privilege mechanism for symlink creation; some filesystems do not support the requested link type.
3. **Do you have permission to operate on the target when using the link?** A symlink that was successfully created can still point to a file the caller lacks permission to read. Renaming or deleting the link entry can succeed while reading the target content fails, and vice versa.

For Unix/POSIX, **9 `rwx` bits** apply to owner/group/others. For *files*, `r` allows reading content, `w` allows modifying content, and `x` allows executing according to OS rules. For *directories*, `r` supports listing names, `w` supports modifying child entries, and `x` allows searching/traversing the path; valid permissions on ancestor directories are required together. The permissions of the symlink itself on many Unix systems do not control reading target data; the target's and path's permissions decide. Do not assume that `chmod` on a symlink will control the target file's permissions as desired.

For hard links, permissions on file content generally apply to **the same object** across all names. Deleting one name usually checks permissions on the directory containing that name, not merely the `w` permission of the file. Systems may restrict creating hard links to files not owned by the caller, forbid hard links to directories, or block risky access patterns.

`Files.isReadable(path)`, `Files.isWritable(path)`, and `Files.isExecutable(path)` only provide a **check at the moment of the call**. Results may not fully reflect ACLs, open file states, sandboxes, mounts, and concurrent changes; they **do not grant permissions**, nor do they replace handling `AccessDeniedException`/`IOException` during the actual operation. Do not build a security pattern like `if (Files.isWritable(p)) Files.writeString(p, ...)` and treat the initial check as a guarantee.

## 4. Support by Operating System and File System

| Environment | Symbolic links | Hard links | Permissions and attributes |
| --- | --- | --- | --- |
| **Linux / Unix** with supporting file system (e.g., ext4) | Usually supports links to files/directories, including relative and non-existent targets. | Usually supports names within the same file store; hard links to directories are usually restricted/forbidden. | POSIX `rwx` mode, owner/group, ACLs if configured by the filesystem; mount/security policies may impose further limits. |
| **macOS** with APFS and standard configuration | Supports symlinks; relative and dangling links behave similarly to Unix. | Supports hard links for files within filesystem boundaries; does not extend to directories. | POSIX permissions, owner/group, and additional ACL/authorization mechanisms. |
| **Windows** with NTFS | Supports filesystem-level symbolic links; creation rights may depend on privileges, Developer Mode, machine policy, and how the JDK/provider invokes APIs. | NTFS supports hard links for files; requires the same volume and OS conditions. | Windows ACLs are the primary mechanism; `DosFileAttributeView` represents attributes like read-only/hidden, **not equivalent** to POSIX `rwx`. |
| **FAT/exFAT, network drives, containers, virtual/third-party providers** | Support depends on filesystem, server, mount, and provider; creation may not work at all. | Similar; spanning filesystems/volumes is usually disallowed. | Attribute views and permission policies may differ from the host OS. |

The examples in the table describe **common configurations**, not a Java contractual guarantee. `System.getProperty("os.name")` only tells you the OS name; it does not tell you whether the drive containing `Path` supports symlinks, hard links, POSIX, or ACLs. Applications need to inspect the **actual file store**, attempt permitted operations, and handle specific errors.

On Windows, Microsoft documentation notes that creating symbolic links via Win32 may require appropriate privileges; the `SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE` flag works under the condition that Developer Mode is enabled. **Do not infer that simply enabling Developer Mode guarantees every JDK/provider build and every volume can create symlinks**; Java only guarantees reporting an error when it cannot be performed. Corporate machines may enforce separate policies. Enabling Developer Mode is a machine-configuration change and is not an automatic or sole fix inside a Java program.

In Docker/Kubernetes, CI, servers using virtual filesystems, or shared folders, code that succeeds on a developer machine can still fail due to user IDs, read-only mounts, symlink policies, volume permissions, or storage drivers. Fallback choices must be based on business requirements: **copying bytes does not preserve the synchronization behavior of hard links**, and writing a path string in configuration does not create a real symlink.

## 5. Checking Attribute Views Properly

Java NIO.2 provides several attribute views:

- `BasicFileAttributeView`: size, timestamps, file type, and file identifier if provided; available via NIO.2 for ordinary files.
- `PosixFileAttributeView`: owner, group, and nine permission bits (`PosixFilePermission`). Use `Files.getPosixFilePermissions` and `Files.setPosixFilePermissions` **only when supported**.
- `AclFileAttributeView`: ACLs consisting of `AclEntry` items and principals when supported by the provider. ACLs are more complex than the three owner/group/others groups and cannot be generally reduced to `chmod 755`.
- `DosFileAttributeView`: DOS attributes such as read-only, hidden, system, and archive. The read-only attribute **is not a complete access-permission model**.
- `FileStore.supportsFileAttributeView("posix")` (or `"acl"`, `"dos"`): identifies view capability of the **file store**, **not** an API to check symlink/hard-link creation capability or current user permissions. A provider may support multiple views simultaneously, including the `dos` view on non-Windows environments.

When you need to inspect the link itself, pass `LinkOption.NOFOLLOW_LINKS` to the appropriate method; when you need the target data's permissions, leave link-following as default while accounting for broken or denied target paths. Some operations modifying attributes of a symlink itself are not supported by providers; avoid calling `Files.setPosixFilePermissions(link, ...)` and assuming you configured independent permissions on the "link".

## 6. Runnable Example: Testing Both Link Types, Handling Lack of Support

Create the file `LinkSupportDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class LinkSupportDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-links-");
        Path original = dir.resolve("source.txt");
        Path symlink = dir.resolve("shortcut.txt");
        Path hardlink = dir.resolve("second-name.txt");
        try {
            Files.writeString(original, "hello", StandardCharsets.UTF_8);
            try {
                // Relative target is resolved from the directory containing shortcut.txt.
                Files.createSymbolicLink(symlink, Path.of("source.txt"));
                System.out.println("symbolic=" + Files.isSymbolicLink(symlink));
                System.out.println("raw-target=" + Files.readSymbolicLink(symlink));
                System.out.println("through-link=" + Files.readString(symlink));
            } catch (IOException | UnsupportedOperationException | SecurityException ex) {
                System.out.println("symbolic-unavailable=" + ex.getClass().getSimpleName());
            }
            try {
                Files.createLink(hardlink, original);
                System.out.println("same-file=" + Files.isSameFile(original, hardlink));
                Files.writeString(hardlink, "updated", StandardCharsets.UTF_8);
                System.out.println("through-original=" + Files.readString(original));
            } catch (IOException | UnsupportedOperationException | SecurityException ex) {
                System.out.println("hard-unavailable=" + ex.getClass().getSimpleName());
            }
            System.out.println("posix-view=" +
                Files.getFileStore(original).supportsFileAttributeView("posix"));
        } finally {
            // Delete the link names first, then delete the file and temporary directory.
            Files.deleteIfExists(symlink);
            Files.deleteIfExists(hardlink);
            Files.deleteIfExists(original);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run with Java 17+:

```bash
javac --release 17 LinkSupportDemo.java
java LinkSupportDemo
```

A run on Linux with a filesystem supporting both link types produces:

```text
symbolic=true
raw-target=source.txt
through-link=hello
same-file=true
through-original=updated
posix-view=true
```

Explanation: the symlink stores the relative path `source.txt`; reading through the symlink returns `hello`. The hard link provides a second name for **the same file object**, so writing `updated` via `second-name.txt` causes reading from `source.txt` to see the new content. On an unsupported machine, `symbolic-unavailable=...` or `hard-unavailable=...` may appear with the specific exception name; `posix-view` also depends on the file store. This is a **conditional output**, not six guaranteed lines on every OS.

The example uses a dedicated directory created via `Files.createTempDirectory` and cleans up in `finally`; for simplicity, if another process intentionally modifies the temporary directory during execution, cleanup may still throw `IOException`. In real applications, log exceptions along with the path/file store and perform cleanup appropriate for resource ownership.

## 7. Runnable Example: Observing and Setting POSIX Permissions When Supported

Create `PermissionProbe.java`:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.util.Set;

public class PermissionProbe {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("nio-permission-", ".txt");
        try {
            FileStore store = Files.getFileStore(file);
            System.out.println("posix=" + store.supportsFileAttributeView("posix"));
            System.out.println("acl=" + store.supportsFileAttributeView("acl"));
            System.out.println("dos=" + store.supportsFileAttributeView("dos"));

            if (store.supportsFileAttributeView("posix")) {
                Set<PosixFilePermission> previous = Files.getPosixFilePermissions(file);
                try {
                    Files.setPosixFilePermissions(file,
                        PosixFilePermissions.fromString("rw-------"));
                    System.out.println("permissions=" + PosixFilePermissions.toString(
                        Files.getPosixFilePermissions(file)));
                } finally {
                    Files.setPosixFilePermissions(file, previous);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 PermissionProbe.java
java PermissionProbe
```

Example output on a specific Linux/JDK system:

```text
posix=true
acl=false
dos=true
permissions=rw-------
```

The first three lines **depend on the Java provider and file store**, not directly on what the OS is; for example, `dos=true` can appear even on Linux. The line `permissions=rw-------` appears only when the POSIX view is supported and the permission change succeeds: owner has read/write, while group and others have no `rwx` bits. The example restores the previous mode in `finally` before deleting the temporary file; ACLs, effective access, and OS policies can still make actual permissions more complex than these nine bits. If changing permissions is denied, `IOException` reports the failure: do not swallow errors and assume security was configured.

For Windows ACLs, use `AclFileAttributeView` after checking support and properly understanding `UserPrincipal` / `AclEntry`. Do not try to use `setPosixFilePermissions` as a substitute for ACLs. If the goal is simply opening a file to read/write, it is usually better to perform the actual NIO operation and handle errors rather than trying to alter system permissions.

## 8. Error Scenarios and Intentional Handling

| Symptom / exception | Cause to check | Appropriate response |
| --- | --- | --- |
| `UnsupportedOperationException` from link creation | Provider does not support the requested operation or attribute. | Report unsupported feature; switch to another approach only if the application contract permits. |
| `AccessDeniedException` / `FileSystemException` | Directory permissions, symlink creation privilege, Windows/Unix policy, mount, filesystem, or file in use. | Log the operation, path, filesystem type, and error message; check permissions/config per environment, do not auto-elevate privileges. |
| `FileAlreadyExistsException` | The `link` name already has an entry, possibly a broken symlink. | Use a new name or a clear conflict-handling policy; **do not** blindly delete existing data. |
| `NoSuchFileException` when reading through link | Link is broken or a path component does not exist. | Distinguish link existence from target existence using `NOFOLLOW_LINKS`. |
| Error creating hard link across volumes | Hard links cannot connect two objects on two different file stores in many filesystems. | Place the link on the same file store or change storage design, understanding that copying is not equivalent to a hard link. |
| `FileSystemLoopException` when traversing with links | A symlink loops back to an ancestor directory causing a cycle. | Disable `FOLLOW_LINKS` if unnecessary; if needed, catch the error, limit depth, and define a cycle-handling policy. |
| `SecurityException` | Access blocked by a security/runtime policy matching the active configuration. | Inspect the blocking mechanism accurately; do not equate it with "unsupported filesystem". |

**Do not check `Files.exists(link)` to definitively decide whether a new link can be created.** A broken symlink can make `exists(link) == false` even though the link entry still occupies the name. Even `exists(link, NOFOLLOW_LINKS)` is only an instantaneous snapshot, vulnerable to races; `createSymbolicLink`/`createLink` calls must still handle `FileAlreadyExistsException` themselves.

Quick example to understand a dangling symlink (only run where symlink creation is permitted):

```java
Path dangling = dir.resolve("broken-link"); // dir already exists
Files.createSymbolicLink(dangling, Path.of("missing.txt"));
System.out.println(Files.exists(dangling)); // usually false: target does not exist yet
System.out.println(Files.exists(dangling, LinkOption.NOFOLLOW_LINKS)); // true: link exists
Files.delete(dangling); // deletes only the link
```

The snippet above is **an illustration depending on a previously created `dir` variable**, not a standalone Java program. The output assumes symlink creation succeeds and no other actor modifies the path.

## 9. Safety and Correctness When Paths Come from Users

- **Avoid symlink traversal:** if the application lets users choose filenames inside a controlled directory, guard against others creating symlinks leading to external files. `base.resolve(userInput).normalize().startsWith(base)` only checks the path lexically, **without verifying** the entity the symlink resolves to.
- **Do not trust check-then-use:** between `toRealPath`/`exists` and `Files.newInputStream` or `Files.delete`, another process can swap the link. Use `LinkOption.NOFOLLOW_LINKS` where APIs allow when you want to operate on the final entry; when accessing an untrusted directory tree, consider `SecureDirectoryStream` (if supported by the provider) or safe file-opening mechanisms provided by the platform.
- **Explicit follow policy:** when scanning folders, backing up, deleting trees, unpacking archives, or syncing data, decide whether to follow symlinks. Blindly following links can cause infinite loops, cross directory boundaries, or touch out-of-scope resources.
- **Do not "fix permission errors" with `chmod 777` / running as Administrator by default:** grant only the necessary permissions to the service account, directories, and objects. Check ACLs, user/group, mount permissions, and policies in the deployment environment.
- **Plan for portability:** Java provides a unified API but does not standardize all OS-level semantics. Any feature requiring symlink/hard-link creation must be tested on the target filesystem in a real environment; fallbacks and error messages must be defined in advance.

## 10. Practical Checklist

1. Determine whether business logic needs a **redirect path** (symlink), **multiple names sharing one object** (hard link), or an **independent data copy** (`Files.copy`): the three goals do not substitute for one another.
2. Identify the source `Path`, link creation location, target existence, and volume/file store relationship. For relative symlinks, compute the target from **the directory containing the link**.
3. Check views via `FileStore` when metadata/permissions are needed; distinguish POSIX, ACL, and DOS; do not use the OS name as a substitute for measuring actual capabilities.
4. Perform actual create/read/delete APIs inside `try`/`catch`, handling permission errors, unsupported operations, broken targets, and name conflicts rather than relying on `exists` as a synchronization lock.
5. Decide clearly when to follow symlinks and when to use `NOFOLLOW_LINKS`; validate paths from untrusted sources and address race conditions.
6. Test on Linux/macOS/Windows or the target deployment environment **with the exact filesystem, user, and mount**; do not test solely on a developer machine.

**Self-Check Knowledge**

- Why does deleting `shortcut.txt` (a symlink) not delete `source.txt`, whereas editing content through a hard link typically changes the data visible under every name?
- Why can `Files.exists(brokenLink)` return `false` while `Files.exists(brokenLink, NOFOLLOW_LINKS)` returns `true`?
- If `FileStore.supportsFileAttributeView("posix")` returns `true`, can you already conclude that creating a symbolic link will succeed? **Not yet:** attribute views and link creation capability/permissions are two separate issues.
- When running the same code on Windows NTFS vs. a FAT/exFAT drive or network drive, which factors can differ? **Supported link types, privilege requirements, ACLs, attributes, mount/driver behavior, and I/O errors.**
- Why can a path normalized with `normalize()` still escape outside the root directory through a symlink? Because `normalize()` does not resolve links on the filesystem.

## Official Documentation

- Java SE 21: [`Files` — `createSymbolicLink`, `createLink`, `readSymbolicLink`, `walkFileTree`, `NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html).
- Java SE 21: [`PosixFileAttributeView` — permissions, owner, group, and mode bits](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html).
- Microsoft Learn: [`CreateSymbolicLinkW` — privileges and unprivileged create flag](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createsymboliclinkw); [Developer Mode on Windows](https://learn.microsoft.com/en-us/windows/advanced-settings/developer-mode).

The descriptions here apply to the standard Java NIO.2 API (Java 17+); actual capabilities always depend on the provider/file store and operating system configuration.