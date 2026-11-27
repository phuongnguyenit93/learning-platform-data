# Paths, Symbolic Links, and Access Permission Checks in Java 17

When working with files and directories, merely concatenating a string like `"data/report.txt"` is not enough to know which object the program is actually accessing or whether it has permission to perform an operation. A path may be relative or absolute; it may contain `.` and `..` components; a component may be a **symbolic link** pointing elsewhere; and access permissions also depend on the operating system, running account, ACLs, mounts, and filesystem state at the moment of the operation.

In Java 17, the modern API for handling these issues lives in **Java NIO.2**, primarily:

- `Path`: represents a path according to a filesystem/provider.
- `Path.of(...)` or `Paths.get(...)`: creates path objects.
- `Files`: inspects, reads attributes, creates, deletes, and operates on files and directories.
- `LinkOption.NOFOLLOW_LINKS`: instructs supported APIs not to follow symbolic links.
- `BasicFileAttributes`, `PosixFileAttributes`, and `AclFileAttributeView`: reads attributes and permissions as supported by the provider.

This lesson focuses on distinguishing a path from a filesystem object, recognizing and handling symbolic links, and checking access permissions without relying on Windows-specific or Unix-specific assumptions.

## 1. Path Represents a Name/Location, Not the File Itself

`Path` is an object representing a path within a filesystem. It does not by itself prove the file exists, does not open the file, and does not store access permission state.

```java
import java.nio.file.Path;

Path relative = Path.of("data", "reports", "summary.txt");
Path absolute = Path.of("/var/app/data/reports/summary.txt");

System.out.println(relative);
System.out.println(absolute);
```

`Path.of(...)` has been available since Java 11; Java 17 can use it directly. `Paths.get(...)` still exists and also creates a `Path`, though `Path.of(...)` is more concise for new code.

Key points to remember:

- A `Path` can be relative or absolute.
- Component separation depends on the filesystem/provider. Avoid manually joining paths with `/` or `\` if you want cross-platform code; use `Path.of("folder", "file.txt")` or `resolve`.
- A `Path` may refer to a file that does not exist yet.
- Two `Path` instances can refer to the same filesystem location even if their string forms differ.
- A path may traverse symbolic links, so the visible name in `Path` is not guaranteed to be the final physical path.

### 1.1. Creating Relative and Absolute Paths

```java
Path config = Path.of("config", "app.properties");

System.out.println(config.isAbsolute()); // false on standard filesystems

Path absoluteConfig = config.toAbsolutePath();
System.out.println(absoluteConfig);
```

`toAbsolutePath()` converts a relative path into an absolute path using the JVM's default working directory. It **does not require the file to exist** and does not follow symbolic links to compute a real path.

To inspect the current working directory:

```java
System.out.println(System.getProperty("user.dir"));
```

The working directory is a property of the process and is not always the directory containing your `.java` or `.jar` files.

### 1.2. Joining Paths with resolve

Avoid manual string concatenation:

```java
// Avoid handling separators manually:
// String fileName = base + "/" + child;
```

Use `resolve`:

```java
Path base = Path.of("data", "exports");
Path file = base.resolve("orders.csv");

System.out.println(file);
```

`resolve` appends a child path to a base path according to `Path` rules. If the passed argument is an absolute path, the result is that absolute path rather than appending to `base`.

```java
Path base = Path.of("data", "exports");
Path child = Path.of("orders.csv");
Path result = base.resolve(child);
```

To construct a sibling path, use `resolveSibling`:

```java
Path report = Path.of("data", "reports", "summary.txt");
Path backup = report.resolveSibling("summary.txt.bak");
```

### 1.3. normalize() Only Normalizes Path Syntax

A path may contain `.` or `..` components:

```java
Path path = Path.of("data", "reports", "..", "logs", ".", "app.log");
Path normalized = path.normalize();

System.out.println(normalized);
```

`normalize()` removes syntactically redundant elements such as `.` and pairs of a directory name followed by `..` where possible. This is a transformation **on the path itself**; it does not access the filesystem and does not check whether the file exists.

Crucially, `normalize()` is not equivalent to finding the real path. If a component is a symbolic link, removing `..` syntactically can yield a different result than actually traversing the filesystem.

Hypothetical example:

```text
/work/link/../result.txt
```

If `/work/link` is a symbolic link pointing to `/outside/project`, filesystem traversal follows the link target before resolving `..`. `normalize()` only inspects component strings and has no knowledge of where the link points. When you need the real path of an existing object, see `toRealPath()` below.

## 2. toRealPath() and How It Differs from normalize()

`Path.toRealPath(...)` asks the filesystem to resolve the path and return the real path of the object. By default, this method follows symbolic links and requires the target object to exist.

```java
import java.io.IOException;
import java.nio.file.Path;

Path path = Path.of("data", "reports", "..", "reports", "summary.txt");

try {
    Path real = path.toRealPath();
    System.out.println(real);
} catch (IOException ex) {
    System.out.println("Cannot resolve path: " + ex.getMessage());
}
```

Differences:

| API | Accesses filesystem? | Requires target to exist? | Symbolic link handling |
| --- | --- | --- | --- |
| `normalize()` | No | No | Does not follow links |
| `toAbsolutePath()` | Does not need to read target attributes | No | Does not automatically follow links |
| `toRealPath()` | Yes | Yes, unless special options apply | Follows links by default |
| `toRealPath(NOFOLLOW_LINKS)` | Yes | Path components are resolved without following links | Does not follow symbolic links per option |

`toRealPath()` can confirm that two different path strings actually point to the same physical location. However, it can throw `IOException` if the path does not exist, is inaccessible, or cannot be resolved.

### 2.1. normalize() Does Not Validate Path Safety

A common bug in applications accepting user-supplied filenames is:

```java
Path target = uploadDirectory.resolve(userInput).normalize();
```

`normalize()` eliminates redundant elements, but **does not guarantee `target` stays inside the upload directory**. For example, a user might enter `../../outside.txt`; even after normalization, the path escapes the root directory.

You can check the path relationship after computing normalized absolute paths:

```java
Path root = uploadDirectory.toAbsolutePath().normalize();
Path target = root.resolve(userInput).normalize();

if (!target.startsWith(root)) {
    throw new SecurityException("Path escapes allowed directory");
}
```

This check helps prevent paths from escaping the root syntactically. However, if the directory contains symbolic links or the environment can be modified concurrently, safer filesystem operations are still needed; checking path strings alone does not solve all link-traversal or race-condition risks.

## 3. What Is a Symbolic Link?

A **symbolic link** (often called a symlink) is a filesystem object containing a reference path pointing to another object. When a program accesses the link using default options, the filesystem typically follows the link to its target.

Diagram:

```text
project/
├── data/
│   └── report.txt
└── latest.txt  ───────────────┐
                              │ symbolic link
                              └──> data/report.txt
```

Here, `latest.txt` is a link; the actual file content resides at `data/report.txt`.

A symbolic link can:

- Point to a file or a directory.
- Point using a relative or absolute path.
- Point to a location on a different filesystem, depending on OS and provider.
- Point to an object that does not exist (dangling/broken link).
- Form link loops or multi-hop link chains.

Do not confuse a symbolic link with a **hard link**. A hard link is another directory entry name referring to the same underlying file object (per filesystem semantics); a symbolic link is a distinct object storing a target path. Java provides separate APIs for both.

## 4. Creating and Detecting Symbolic Links

### 4.1. Creating a Symbolic Link with Files.createSymbolicLink

API:

```java
Files.createSymbolicLink(link, target);
```

Where:

- `link` is the path where the symbolic link entry will be created.
- `target` is the path the link will reference.

Example:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path directory = Path.of("demo");
Path target = directory.resolve("original.txt");
Path link = directory.resolve("shortcut.txt");

Files.createDirectories(directory);
Files.writeString(target, "Original content");

try {
    Files.createSymbolicLink(link, Path.of("original.txt"));
    System.out.println(Files.readString(link));
} catch (UnsupportedOperationException ex) {
    System.out.println("Filesystem/provider does not support symbolic links");
} catch (IOException | SecurityException ex) {
    System.out.println("Cannot create symbolic link: " + ex.getMessage());
}
```

The target `original.txt` is a relative path. It is resolved relative to the directory containing the link `shortcut.txt`, not the JVM's working directory.

Permission to create symbolic links depends on the platform and system configuration. On some Windows environments, creating symlinks requires elevated privileges or Developer Mode; on Unix-like systems, permissions and filesystem policies also apply. Consequently, portable code should handle `IOException`, `SecurityException`, and `UnsupportedOperationException` rather than assuming every host permits creating links.

### 4.2. Checking Whether a Path Is a Symbolic Link

Use `Files.isSymbolicLink(path)`:

```java
if (Files.isSymbolicLink(link)) {
    System.out.println("This is a symbolic link");
} else {
    System.out.println("Not a symbolic link");
}
```

This method inspects the object at the path itself; it does not tell you whether the link's target exists.

### 4.3. Reading the Target Path with readSymbolicLink

```java
Path target = Files.readSymbolicLink(link);
System.out.println(target);
```

`readSymbolicLink` returns the target path stored inside the symbolic link. If the link stores a relative target, the returned `Path` is also relative. This API **does not resolve the final real path**; to follow links to the real object, call `toRealPath()` on the appropriate path.

If `path` is not a symbolic link, `readSymbolicLink` throws `NotLinkException`. If the link cannot be read or a filesystem error occurs, it may throw `IOException`.

## 5. Valid Links, Dangling Links, and NOFOLLOW_LINKS

A symbolic link can exist even if its target was deleted or never created. This is called a **dangling symbolic link**.

Example:

```java
Path link = Path.of("demo", "missing-link");

Files.createSymbolicLink(link, Path.of("not-created.txt"));
```

If creating the link succeeds while `not-created.txt` does not exist:

- `Files.isSymbolicLink(link)` returns `true`.
- `Files.exists(link)` follows the link by default, so it normally returns `false` because the target does not exist.
- `Files.exists(link, LinkOption.NOFOLLOW_LINKS)` inspects the link itself and can return `true`.

Verification example:

```java
boolean linkObjectExists =
        Files.exists(link, LinkOption.NOFOLLOW_LINKS);
boolean targetExists =
        Files.exists(link);

System.out.println("Link object: " + linkObjectExists);
System.out.println("Target: " + targetExists);
```

### 5.1. What Is LinkOption.NOFOLLOW_LINKS Used For?

`LinkOption.NOFOLLOW_LINKS` tells APIs supporting this option **not to follow the final symbolic link** when performing the operation. It is useful when inspecting or reading attributes of the link object itself rather than its target.

Several APIs accept this option:

- `Files.exists(path, NOFOLLOW_LINKS)`
- `Files.notExists(path, NOFOLLOW_LINKS)`
- `Files.isDirectory(path, NOFOLLOW_LINKS)`
- `Files.isRegularFile(path, NOFOLLOW_LINKS)`
- `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)`
- `Path.toRealPath(NOFOLLOW_LINKS)`
- Certain file-opening operations accept `LinkOption.NOFOLLOW_LINKS` as an `OpenOption`, if supported by the provider.

Example reading attributes of the link itself:

```java
import java.nio.file.LinkOption;
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attributes = Files.readAttributes(
        link,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS
);

System.out.println(attributes.isSymbolicLink());
System.out.println(attributes.isRegularFile());
```

If the path is a symbolic link, `isSymbolicLink()` reflects that. With the no-follow option, `isRegularFile()` is `false` for the link object itself, even if the link points to a regular file.

**Note:** `NOFOLLOW_LINKS` is not a universal switch for every `Files` API. Only pass it to methods whose signatures accept it; never assume every operation automatically skips links.

### 5.2. exists and notExists Can Both Return false

`Files.exists(...)` and `Files.notExists(...)` are not always strict logical opposites. If Java cannot determine status due to insufficient permissions or filesystem access errors, both can return `false`.

Therefore:

```java
if (!Files.exists(path)) {
    // Cannot conclude with certainty that path does not exist.
}
```

When exact status matters, interpret results in context and perform the required operation with appropriate exception handling. Existence checks are only point-in-time advisories.

## 6. Following Targets and Safe Symbolic Link Handling

### 6.1. toRealPath() Follows Links by Default

Suppose `shortcut.txt` points to `original.txt`:

```java
Path realTarget = shortcut.toRealPath();
System.out.println(realTarget);
```

If the target exists and is accessible, the result is the real path after resolving links. This is useful for:

- Comparing the real paths of two filenames.
- Displaying the final destination a link resolves to.
- Logging filesystem-resolved paths.
- Locating the existing target of a symlink.

If the link is broken or the target cannot be resolved, `toRealPath()` can throw `IOException`.

### 6.2. toRealPath(NOFOLLOW_LINKS) Does Not Follow Symbolic Links

When you want to preserve a link as part of the path, call:

```java
Path pathWithoutFollowingLinks =
        shortcut.toRealPath(LinkOption.NOFOLLOW_LINKS);
```

This option alters how symbolic links are resolved; do not think the method simply returns the raw input string unchanged. It is still a filesystem operation and can still fail if required components cannot be resolved.

### 6.3. Deleting the Link vs. Deleting the Target

`Files.delete(link)` deletes the symbolic link itself, not the object it points to:

```java
Files.delete(link);
```

This is crucial behavior during cleanup. If you intend to delete the target, identify and operate on the target path explicitly; do not accidentally delete real data when cleaning up a shortcut.

If `link` is a dangling link, `Files.delete(link)` can still delete the link object because the link entry itself exists even though its target does not.

## 7. Checking Access Permissions with Files

Java provides several common permission checks:

```java
Files.isReadable(path);
Files.isWritable(path);
Files.isExecutable(path);
```

These methods return a `boolean`, useful for displaying status or guiding UI behavior:

```java
if (Files.isReadable(path)) {
    System.out.println("Readable per current check");
}

if (Files.isWritable(path)) {
    System.out.println("Writable per current check");
}

if (Files.isExecutable(path)) {
    System.out.println("Executable per current check");
}
```

They follow symbolic links by default and inspect permissions of the target object.

### 7.1. isReadable, isWritable, and isExecutable Do Not Throw IOException

Unlike many actual read/write operations, these methods return `false` if permissions cannot be determined or access is lacking. Examples include:

- The path does not exist.
- The current process lacks access rights.
- The provider cannot determine permissions.
- The filesystem or device has an issue.

Do not treat `false` as a single root cause; to know the specific reason, attempt the real operation and inspect the resulting exception.

### 7.2. Permission Checks Do Not Guarantee the Next Operation Succeeds

This point is critical:

```java
if (Files.isWritable(path)) {
    Files.writeString(path, "Updated");
}
```

Between `isWritable` returning `true` and `writeString` executing, permissions may change, the file may be deleted or replaced, the filesystem may change state, or a symbolic link's target may be swapped.

This issue falls under **time-of-check to time-of-use (TOCTOU)**: checking and using happen at two separate moments.

Therefore, the more reliable approach is to perform the required operation and handle the outcome:

```java
try {
    Files.writeString(path, "Updated");
    System.out.println("Write succeeded");
} catch (IOException ex) {
    System.out.println("Unable to write file: " + ex.getMessage());
}
```

`isWritable()` can be used for early user feedback, while `writeString()` provides the authoritative outcome of the write operation.

## 8. Reading POSIX Permissions When Supported by the Filesystem

On POSIX-compliant systems, Java provides `PosixFilePermissions` and `PosixFileAttributeView`. Basic POSIX permissions consist of three groups:

- **Owner:** file owner.
- **Group:** owning group.
- **Others:** all other users.

Each group has three permissions:

- `READ`: read access.
- `WRITE`: write access.
- `EXECUTE`: execute access (for directories, usually means search/traverse permission).

Example reading permissions:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.Set;

Path file = Path.of("data", "report.txt");

try {
    Set<PosixFilePermission> permissions =
            Files.getPosixFilePermissions(file);

    System.out.println(permissions);
} catch (UnsupportedOperationException ex) {
    System.out.println("Filesystem does not support POSIX permissions");
} catch (IOException ex) {
    System.out.println("Cannot read permissions: " + ex.getMessage());
}
```

`Files.getPosixFilePermissions(path)` reads the POSIX permissions of the object; by default, APIs in this group follow symbolic links. An overload accepting `LinkOption...` is available to request not following links if supported by the provider.

### 8.1. Formatting as rwxr-x---

You can use `PosixFilePermissions.toString(...)`:

```java
String mode = PosixFilePermissions.toString(permissions);
System.out.println(mode);
```

For example, `rw-r-----` means:

- Owner: read and write.
- Group: read only.
- Others: no permissions.

This is the standard POSIX representation, not a universal permission format across all filesystems.

### 8.2. Setting POSIX Permissions

```java
Set<PosixFilePermission> permissions =
        PosixFilePermissions.fromString("rw-r-----");
Files.setPosixFilePermissions(file, permissions);
```

This operation can throw `IOException`, `UnsupportedOperationException`, or `SecurityException` depending on the environment and process privileges.

Do not call `setPosixFilePermissions` without verifying whether the filesystem supports POSIX. Windows typically uses ACLs rather than the traditional POSIX model; its provider may not support POSIX APIs.

## 9. Access Permissions and ACLs on Windows or Other Filesystems

Not every filesystem uses a POSIX permission model. Some environments use an **Access Control List (ACL)**, where permissions are assigned to specific users or groups via ACL entries.

Java NIO provides:

- `AclFileAttributeView`
- `AclEntry`
- `AclEntryPermission`
- `AclEntryType`
- `UserPrincipal`
- `UserPrincipalLookupService`

You can check whether the provider supports an ACL view:

```java
AclFileAttributeView aclView = Files.getFileAttributeView(
        path,
        AclFileAttributeView.class
);

if (aclView == null) {
    System.out.println("Provider does not support ACL view");
} else {
    List<AclEntry> entries = aclView.getAcl();
    entries.forEach(System.out::println);
}
```

To compile the snippet above, include imports:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclEntry;
import java.nio.file.attribute.AclFileAttributeView;
import java.util.List;
```

`getFileAttributeView` can return `null` if the provider does not support the requested view. Reading ACLs can throw `IOException` or `SecurityException`.

### 9.1. Why You Should Not Infer Permissions from rwx Strings Across All OSes

POSIX permissions and Windows ACLs do not map one-to-one:

- POSIX typically models owner/group/others permissions.
- ACLs can contain multiple entries for individual users/groups and finer-grained permissions.
- Effective access also depends on inherited permissions, group memberships, system policies, mounts, and process accounts.

If an application needs to know whether it can perform an operation, `Files.isReadable`, `isWritable`, `isExecutable`, or the actual read/write operation is closer to what you need. If the application administers detailed permissions, use the attribute view suited to the filesystem and handle unsupported environments.

## 10. Checking Object Types: File, Directory, and Symbolic Link

The following methods follow symbolic links by default:

```java
Files.isRegularFile(path);
Files.isDirectory(path);
Files.isSymbolicLink(path);
```

Example:

```java
if (Files.isRegularFile(path)) {
    System.out.println("Path leads to a regular file");
} else if (Files.isDirectory(path)) {
    System.out.println("Path leads to a directory");
} else if (Files.isSymbolicLink(path)) {
    System.out.println("Path is a symbolic link");
} else {
    System.out.println("Other type or unknown");
}
```

The order in that example is intentional: `isRegularFile` and `isDirectory` follow links by default; if a link points to a file, the first branch matches and execution never reaches `isSymbolicLink`. If the goal is detecting a link object, call `Files.isSymbolicLink(path)` separately or use an attribute API with `NOFOLLOW_LINKS`.

```java
boolean isLink = Files.isSymbolicLink(path);
boolean targetIsFile = Files.isRegularFile(path);
boolean linkItselfIsFile = Files.isRegularFile(
        path, LinkOption.NOFOLLOW_LINKS
);
```

Variable names clarify whether you are asking about the link itself or its target. `isRegularFile(path, NOFOLLOW_LINKS)` does not treat a symbolic link as a regular file merely because its target is one.

## 11. Reading Attributes with BasicFileAttributes

When multiple pieces of metadata are needed at once, `Files.readAttributes(...)` reads a group of attributes together:

```java
import java.nio.file.attribute.BasicFileAttributes;

BasicFileAttributes attrs = Files.readAttributes(
        path,
        BasicFileAttributes.class
);

System.out.println("Directory: " + attrs.isDirectory());
System.out.println("Regular file: " + attrs.isRegularFile());
System.out.println("Symbolic link: " + attrs.isSymbolicLink());
System.out.println("Size: " + attrs.size());
System.out.println("Modified: " + attrs.lastModifiedTime());
```

By default, the API follows symbolic links. To read attributes of the link object itself:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS
);
```

`BasicFileAttributes` can report:

- Whether the object is a directory, regular file, symbolic link, or other type.
- Size in bytes.
- Creation, last-access, and last-modified timestamps (if provided by the provider).
- File key, if the provider supports filesystem object identifiers.

Reading attributes can still fail with `IOException`, `SecurityException`, or due to concurrent changes. Never treat a single attribute read as proof that state will remain unchanged in the next step.

## 12. Comprehensive Example: Checking Links and Permissions Before Reading

The following example takes a path, reports whether the path itself is a symbolic link, checks target existence, prints read/write/execute status, and attempts to read content:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;

public class PathAccessDemo {
    public static void main(String[] args) {
        Path path = Path.of(args.length == 0 ? "data/report.txt" : args[0]);

        System.out.println("Path: " + path.toAbsolutePath());
        System.out.println("Is symbolic link: " + Files.isSymbolicLink(path));
        System.out.println("Exists (follow link): " + Files.exists(path));
        System.out.println("Link object exists: "
                + Files.exists(path, LinkOption.NOFOLLOW_LINKS));

        System.out.println("Readable: " + Files.isReadable(path));
        System.out.println("Writable: " + Files.isWritable(path));
        System.out.println("Executable: " + Files.isExecutable(path));

        try {
            System.out.println("Real path: " + path.toRealPath());
            System.out.println("Content:");
            System.out.println(Files.readString(path));
        } catch (IOException ex) {
            System.out.println("Unable to resolve or read file: "
                    + ex.getMessage());
        }
    }
}
```

Run:

```bash
javac --release 17 PathAccessDemo.java
java PathAccessDemo data/report.txt
```

This example is for inspection and diagnostics. In production applications, when the goal is reading data, perform `Files.readString` or open a stream and handle `IOException`; the preceding permission checks merely provide supplemental context.

## 13. Constructing and Validating Paths Inside an Allowed Directory

When an application receives a filename from a user, such as an uploaded filename or report name, prevent `..` inputs from escaping the root directory.

A syntactic validation step:

```java
static Path resolveInside(Path root, String userFileName) {
    Path normalizedRoot = root.toAbsolutePath().normalize();
    Path candidate = normalizedRoot.resolve(userFileName).normalize();

    if (!candidate.startsWith(normalizedRoot)) {
        throw new SecurityException("Path escapes root directory");
    }
    return candidate;
}
```

Example:

```java
Path root = Path.of("uploads");

Path safe = resolveInside(root, "2026/report.pdf");
Path rejected = resolveInside(root, "../../private/secret.txt");
```

`startsWith(Path)` compares by path components, which is safer than string comparisons like `candidate.toString().startsWith(root.toString())`. String prefix checks fail when directory names share a string prefix, such as `uploads-old` starting with `uploads` without being a subdirectory of `uploads`.

### 13.1. Limitations of startsWith Checks

The check above only stops certain paths from escaping the root syntactically. It is insufficient if an attacker can create or replace symbolic links inside the upload directory.

Example:

```text
uploads/
└── public-link -> /private
```

The input `public-link/secret.txt` contains no `..`, and the normalized path still starts with `uploads`. Yet when the filesystem follows the link, the real path leads to `/private/secret.txt`.

In environments exposed to concurrent modification, consider:

- Verifying real paths after creating or resolving required directories.
- Prohibiting untrusted users from creating symbolic links inside storage areas.
- Opening files with options that do not follow symbolic links when supported by the API/provider and suitable for requirements.
- Using `SecureDirectoryStream` when supported by the provider and safe relative operations inside an open directory are needed.
- Keeping ownership of the root and parent directories under a trusted account.

No single `normalize()` or `startsWith()` call solves all filesystem race conditions on its own.

## 14. SecureDirectoryStream and Safe Relative Operations

`SecureDirectoryStream` provides directory operations designed to reduce risks when paths are modified concurrently on certain filesystems/providers. It is not supported by every provider.

You can check via `DirectoryStream`:

```java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    if (stream instanceof SecureDirectoryStream<Path> secure) {
        // Provider supports operations relative to the open directory.
    } else {
        // Provider does not supply SecureDirectoryStream.
    }
}
```

When supported, this API provides operations such as `newByteChannel`, `newDirectoryStream`, `deleteFile`, `deleteDirectory`, and `move` relative to the open directory. `NOFOLLOW_LINKS` can be used on supported operations to avoid following the final link.

This is a specialized tool for applications needing safe filesystem operations in multi-process environments or with untrusted data. For standard applications, using `Path`, `Files`, and proper exception handling covers most needs. Do not assume every OS provides `SecureDirectoryStream`; always handle the case where the provider does not support it.

## 15. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `Files.exists(link)` returns `false` even though the link object is on disk. | API follows links by default and the target does not exist. | Check `Files.exists(link, NOFOLLOW_LINKS)` and `Files.isSymbolicLink(link)`. |
| `toRealPath()` throws `IOException`. | File does not exist, link is broken, permission is denied, or filesystem error occurred. | Inspect the cause and handle the exception; do not substitute `normalize()` when a real path is required. |
| `normalize()` keeps the path under root, yet the operation accesses outside. | An intermediate component is a symbolic link. | Inspect links, control root directories, and use safer file-opening strategies. |
| `isWritable()` returns `true` yet writing still fails. | Permissions or file state changed after the check; actual write may be denied. | Perform the write and handle `IOException`. |
| `getPosixFilePermissions()` throws `UnsupportedOperationException`. | Provider does not support POSIX permission views. | Check ACLs or use general permission checks; handle platform differences. |
| `readSymbolicLink()` throws `NotLinkException`. | Path is not a symbolic link. | Check `Files.isSymbolicLink` or handle the exception. |
| Creating symbolic links fails on another machine. | Operating systems, filesystems, or privilege policies differ. | Handle `IOException`, `SecurityException`, and `UnsupportedOperationException`; make no environment assumptions. |
| Comparing path strings gives wrong answers. | Separators, case sensitivity, `..`, symlinks, or providers differ. | Use `Path` APIs and `Files.isSameFile` when both objects exist and file identity must be compared. |
| Assuming `Files.notExists(path)` is always the negation of `exists`. | Provider may be unable to determine status. | Handle the case where both return `false`; perform the required operation and catch exceptions. |

## 16. Practice Exercises

### Exercise 1 — Distinguishing normalize and toRealPath

Construct a path containing `.` and `..` components. Print the results of `normalize()` and `toRealPath()`. Explain which operation only handles syntax and which requires the filesystem.

### Exercise 2 — Creating a Symbolic Link

Create `original.txt`, create a symbolic link `shortcut.txt` pointing to it, and read the content through the link. Then delete the original file and observe:

- `Files.isSymbolicLink(shortcut)`.
- `Files.exists(shortcut)`.
- `Files.exists(shortcut, NOFOLLOW_LINKS)`.

### Exercise 3 — Checking Permissions

Write a program that accepts a `Path` and prints `isReadable`, `isWritable`, and `isExecutable`. Perform an actual read or write inside a `try/catch` block and explain why the check result does not guarantee the subsequent operation succeeds.

### Exercise 4 — POSIX and ACLs

Attempt to read `PosixFilePermissions` on the current filesystem. If unsupported, inspect `AclFileAttributeView` and explain why the two permission models cannot fully substitute for one another.

### Exercise 5 — Preventing Path Traversal

Write a function that only accepts filenames inside an `uploads` directory. Test inputs `report.pdf`, `2026/report.pdf`, `../secret.txt`, and `sub/../../secret.txt`. Then explain why symbolic links inside the directory can still render syntactic checks insufficient.

### Exercise 6 — Dangling Symbolic Links

Create a symbolic link pointing to a non-existent file. Use `readAttributes(..., NOFOLLOW_LINKS)` to verify the link object still exists and is of symbolic-link type. Try calling `toRealPath()` and explain the resulting exception.

## 17. Official Java 17 Documentation

- [Java SE 17 API — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): representing, joining, normalizing, and resolving paths.
- [Java SE 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): checking existence/permissions, reading attributes, creating links, deleting, and file operations.
- [Java SE 17 API — LinkOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): options for symbolic link handling.
- [Java SE 17 API — BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html): basic attributes and identifying symbolic links.
- [Java SE 17 API — PosixFilePermissions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html): converting and formatting POSIX permissions.
- [Java SE 17 API — AclFileAttributeView](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/AclFileAttributeView.html): accessing ACL permission lists when supported by the provider.
- [Java SE 17 API — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): filesystem operations relative to an open directory.

When handling files in Java 17, clearly separate **the written path**, **the object the filesystem actually resolves**, and **the permissions the process holds at the moment of the operation**. `normalize()` handles path structure; `toRealPath()` resolves paths through the filesystem; `NOFOLLOW_LINKS` inspects the link object itself; and `isReadable`/`isWritable` are merely point-in-time checks. When reading, writing, creating, or deleting files, performing the actual operation and handling exceptions remains the decisive step.
