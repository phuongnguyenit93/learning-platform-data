# Testing Symbolic Links, Permissions, and Platform-Specific Behavior in Java NIO.2

## 1. Lesson Goal

A piece of I/O code that runs fine on Linux can fail on Windows, macOS, network filesystems, USB drives, or virtual filesystems. The causes usually involve **symbolic links**, **file permissions**, **file attribute views**, provider policies, and changes occurring between the time a path is checked and the time it is used.

For example, the following code is not a safety guarantee:

```java
if (Files.exists(path) && Files.isReadable(path)) {
    // Does not guarantee the subsequent read will succeed.
    String content = Files.readString(path);
}
```

This is a snippet, not a standalone program. After the check, the file may be deleted, have its permissions changed, be renamed, be replaced with a symbolic link, or be locked by another mechanism; `readString` can still throw `IOException`.

After this lesson, you will be able to:

1. Check whether a `Path` is a symbolic link, read the link target, and distinguish **following** from **`NOFOLLOW_LINKS`**.
2. Explain why a broken link can give `Files.exists(path) == false` while `Files.exists(path, NOFOLLOW_LINKS) == true`.
3. Inspect basic attributes and detect support for **POSIX permissions**, **DOS attributes**, or **ACLs** without assuming every platform provides them.
4. Distinguish `Files.isReadable`/`isWritable`/`isExecutable` from reliable access checks; understand **TOCTOU** races.
5. Write Java 17+ examples and tests whose **platform-dependent outcomes are explicitly identified**, instead of treating Linux behavior as the standard across all operating systems.
6. Handle unsupported operations, missing permissions, symbolic-link loops, temporary paths, and safe cleanup.

Within **Testing and Diagnostics**, the focus is knowing **how to observe, verify, and draw accurately scoped conclusions**, rather than trying to bypass OS access controls.

## 2. What Is a Symbolic Link?

A symbolic link (*symlink*) is a filesystem entry holding a reference to a target path. It is **not** a copy of the target file's content, and it is not the same as a **hard link**.

```text
work/
  actual.txt       content: "HELLO"
  shortcut.txt -->  actual.txt      (relative symbolic link)
```

When a program accesses `shortcut.txt`, many `Files` operations **follow the symlink** to `actual.txt` by default; certain operations are designed to inspect the link entry itself.

Distinguish carefully:

- **Link path**: the path where the symbolic link resides, such as `work/shortcut.txt`.
- **Link target**: the target value stored inside the link, such as `actual.txt` or an absolute path.
- **Resolved target**: the path obtained when the system resolves a relative target against **the directory containing the link**, not against the Java process's working directory by default.
- **Dangling/broken link**: the link entry exists, but its target does not exist or cannot be resolved.
- **Link cycle**: a chain of links or a directory link forming a loop when followed.

For example, `Files.readSymbolicLink(link)` returns the target stored in the link and **is not required to return an absolute path**. If the target is relative, the resolution context is the directory containing the link.

## 3. Important Methods and Options

| API | Purpose | Notes |
| --- | --- | --- |
| `Files.isSymbolicLink(path)` | Asks whether the entry is a symbolic link | If indeterminate, may return `false` |
| `Files.createSymbolicLink(link, target)` | Creates a symlink; depends on provider/OS capability | May be unsupported or lack permission |
| `Files.readSymbolicLink(link)` | Reads the target stored inside the link | Target may be relative or non-existent |
| `Files.exists(path)` | Checks whether the path exists under default follow rules | Returns `false` when indeterminate or link target is missing |
| `Files.exists(path, NOFOLLOW_LINKS)` | Checks the link entry itself without following the target | Can be `true` even if target is missing |
| `Files.isRegularFile(path, NOFOLLOW_LINKS)` | Checks the type of the entry itself | A symlink is not considered a regular file |
| `Files.readAttributes(path, BasicFileAttributes.class, options)` | Reads type, size, timestamps, and file key | Can throw `IOException`; useful for distinguishing errors |
| `Path.toRealPath(options)` | Returns the real path per provider contract | Not a standalone authorization mechanism |
| `Files.isSameFile(a, b)` | Checks if two paths refer to the same file when possible | Can access the filesystem and throw `IOException` |
| `Files.delete(link)` | Deletes the specified directory entry | Deleting a symlink does not delete its target |
| `Files.walkFileTree(...)` | Walks a directory tree | Does not follow symlinks by default; `FOLLOW_LINKS` changes behavior |

Common imports:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
```

This is the import set used by the snippets in this lesson. When catching failures, use `IOException` and its subclasses or `UnsupportedOperationException` as dictated by the API.

## 4. What Does `NOFOLLOW_LINKS` Exactly Mean?

`LinkOption.NOFOLLOW_LINKS` controls whether symbolic links are followed for **APIs that accept `LinkOption...` or honor this option per contract**.

Suppose:

```text
dir/
  item.txt
  link.txt -> item.txt
  broken.txt -> missing.txt
```

On a system supporting symlinks with intact state:

| Check | `item.txt` | `link.txt` | `broken.txt` |
| --- | --- | --- | --- |
| `Files.exists(path)` | true | true | false |
| `Files.exists(path, NOFOLLOW_LINKS)` | true | true | true |
| `Files.isSymbolicLink(path)` | false | true | true |
| `Files.isRegularFile(path)` | true | true | false |
| `Files.isRegularFile(path, NOFOLLOW_LINKS)` | true | false | false |
| `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS).isSymbolicLink()` | false | true | true |

The table shows **normal local files with permissions and accurate provider classification**; it does not promise `Files.exists` always returns true/false as shown when I/O errors or insufficient access occur.

**Two warnings:**

1. Not every method on `Files` accepts or obeys `NOFOLLOW_LINKS` in the same way; read the Javadoc for the specific method.
2. `NOFOLLOW_LINKS` typically controls following **the final symbolic link** for the invoked API; it **does not automatically guarantee that no parent directory component is a symlink or gets swapped mid-operation**.

If a security requirement states "must never escape the root directory even when symlinks exist in the path," checking `normalize()` or `exists(..., NOFOLLOW_LINKS)` alone is not enough.

## 5. Complete Java 17+ Example: Valid Symlink and Broken Link

Create **`SymbolicLinkInspectionDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class SymbolicLinkInspectionDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-symlink-");
        Path actual = dir.resolve("actual.txt");
        Path link = dir.resolve("shortcut.txt");
        Path broken = dir.resolve("broken.txt");

        try {
            Files.writeString(actual, "HELLO");

            boolean linksAvailable;
            try {
                Files.createSymbolicLink(link, Path.of("actual.txt"));
                Files.createSymbolicLink(broken, Path.of("missing.txt"));
                linksAvailable = true;
            } catch (UnsupportedOperationException
                     | IOException | SecurityException ex) {
                linksAvailable = false;
            }

            System.out.println("symbolicLinksAvailable=" + linksAvailable);

            if (linksAvailable) {
                System.out.println("linkIsSymbolic="
                        + Files.isSymbolicLink(link));
                System.out.println("linkTargetIsRelative="
                        + !Files.readSymbolicLink(link).isAbsolute());
                System.out.println("regularWhenFollowed="
                        + Files.isRegularFile(link));
                System.out.println("regularWhenNotFollowed="
                        + Files.isRegularFile(
                                link, LinkOption.NOFOLLOW_LINKS));

                BasicFileAttributes attrs = Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);
                System.out.println("attributesSaySymbolic="
                        + attrs.isSymbolicLink());

                System.out.println("brokenExistsFollow="
                        + Files.exists(broken));
                System.out.println("brokenExistsNoFollow="
                        + Files.exists(broken, LinkOption.NOFOLLOW_LINKS));
                System.out.println("sameAsActual="
                        + Files.isSameFile(link, actual));

                Files.delete(link); // deletes link, does not delete actual
                System.out.println("targetSurvivedDelete="
                        + Files.exists(actual));
            }
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(broken);
            Files.deleteIfExists(actual);
            Files.deleteIfExists(dir);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SymbolicLinkInspectionDemo.java
java SymbolicLinkInspectionDemo
```

**Stdout when the platform supports symlink creation and I/O succeeds:**

```text
symbolicLinksAvailable=true
linkIsSymbolic=true
linkTargetIsRelative=true
regularWhenFollowed=true
regularWhenNotFollowed=false
attributesSaySymbolic=true
brokenExistsFollow=false
brokenExistsNoFollow=true
sameAsActual=true
targetSurvivedDelete=true
```

If the provider or execution privileges **disallow creating symbolic links**, the first line may be:

```text
symbolicLinksAvailable=false
```

and the program skips the symlink checks. Observing `false` alone does not prove "Windows does not support symlinks": the cause can be privileges, filesystem, policy, provider, or an I/O condition. Do not write tests requiring symlinks to succeed on every CI runner.

**Explanation:**

- `createSymbolicLink(link, Path.of("actual.txt"))` creates a relative target: the path is resolved from **the directory containing `shortcut.txt`**.
- `readSymbolicLink(link).isAbsolute()` is `false` because the stored target is relative.
- Without `NOFOLLOW_LINKS`, `isRegularFile(link)` checks the target `actual.txt`; with `NOFOLLOW_LINKS`, it checks the link entry itself.
- `BasicFileAttributes` provides file-type inspection with explicit I/O error reporting.
- `broken.txt` still has a symlink entry, while target `missing.txt` does not exist, so the two `exists` checks differ.
- `Files.delete(link)` does not delete `actual.txt`.
- Cleanup attempts to delete each created entry; the example alters no files outside the temporary directory it created.

The `catch` around link creation handles only platform-capability failures to **skip link checks**. Subsequent I/O operations can still fail; let those exceptions surface as test failures rather than hiding all errors with `catch (Exception)`.

## 6. Do Not Confuse Symlinks with Hard Links or Desktop Shortcuts

A **hard link** is another directory entry pointing to the same file object, created via `Files.createLink(link, existing)` when supported by the provider/filesystem. It is generally not reported as a symbolic link by `Files.isSymbolicLink()`.

| Property | Symbolic Link | Hard Link |
| --- | --- | --- |
| Can target be absent? | Yes | Usually must point to an existing file |
| `Files.isSymbolicLink` | `true` for recognized valid symlinks | `false` |
| `Files.readSymbolicLink` | Reads stored target string | Not applicable |
| Deleting one entry | Removes link; does not delete target | Removes one directory entry; data can persist via other hard links |
| Supportability | May be restricted by OS/policy/provider | May vary by filesystem/provider |
| Testing impact | Test follow/`NOFOLLOW` | Test file identity and link counts by OS when appropriate |

Windows `.lnk` shortcut files are typically **shell-handled regular files**, not filesystem symbolic links recognized by `Files.isSymbolicLink`. Likewise, GUI aliases and junctions/reparse points have platform-specific semantics; do not assume all link types behave uniformly through `java.nio.file.Files`.

## 7. Access Permissions in Java: Checking Differs from Opening

Convenient probe methods:

```java
boolean readable = Files.isReadable(path);
boolean writable = Files.isWritable(path);
boolean executable = Files.isExecutable(path);
```

This is a snippet requiring `path`. These methods are useful for **displaying observed status** or fast-path hints, yet:

- Returning `true` does not promise the next `Files.newInputStream`/`newOutputStream` will succeed.
- Returning `false` can mean no permission **or inability to determine** permissions at that moment.
- Effective access can involve owner, group, ACLs, sandbox policies, share modes, network mounts, or process identity.
- The file can have its permissions changed, be deleted, or be replaced with a link between check and operation.
- Do not infer from `isWritable` that disk space, quotas, or storage health are sufficient.

The right approach is to **perform the intended I/O operation and catch resulting exceptions**, instead of treating `isReadable` as a user authorization check.

Example:

```java
try (var in = Files.newInputStream(path)) {
    // Process content and verify I/O results.
} catch (java.nio.file.NoSuchFileException ex) {
    // File/path does not exist at operation time.
} catch (java.nio.file.AccessDeniedException ex) {
    // OS/provider denied access.
} catch (java.io.IOException ex) {
    // Other I/O errors: link loops, device, filesystem...
}
```

This is a snippet, not a standalone program. Specific exception subclasses do not necessarily appear identically across every provider; many failures surface as `FileSystemException` or general `IOException`. **Never interpret `AccessDeniedException` as a substitute for business authorization**; the OS and the application have distinct permission models.

## 8. Basic Attributes Are the Portable Starting Point

`BasicFileAttributes` exposes fundamental attributes:

```java
BasicFileAttributes info = Files.readAttributes(
        path, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

System.out.println(info.isRegularFile());
System.out.println(info.isDirectory());
System.out.println(info.isSymbolicLink());
System.out.println(info.isOther());
System.out.println(info.size());
```

This snippet requires `path`, imports, and `IOException` handling.

`BasicFileAttributes` also provides `lastModifiedTime()`, `creationTime()`, `lastAccessTime()`, and `fileKey()`. Never assume:

- Every filesystem stores `creationTime` with the same meaning.
- Timestamps have identical precision or update policies across OSes.
- `fileKey()` is always non-null, permanently stable, or usable as a public identifier.
- `size()` of a symbolic link with `NOFOLLOW_LINKS` equals the target's content byte length.
- All attributes are read atomically against concurrent modifications: Javadoc allows provider-dependent differences.

When you must distinguish "not a symbolic link" from "indeterminate due to an I/O error," use `readAttributes(..., NOFOLLOW_LINKS)` and handle exceptions rather than calling `Files.isSymbolicLink` and treating `false` as definitive proof.

## 9. Platform-Specific Attribute Views

Java NIO.2 defines multiple attribute view interfaces, though actual support depends on the filesystem/provider:

| View | Java API | Typical Information |
| --- | --- | --- |
| Basic | `BasicFileAttributeView` | Entry type, size, timestamps, file key |
| POSIX | `PosixFileAttributeView` | Owner, group, POSIX permission bits |
| DOS | `DosFileAttributeView` | Readonly, hidden, archive, system flags |
| Owner | `FileOwnerAttributeView` | Owner user principal |
| ACL | `AclFileAttributeView` | ACE list and owner |
| User-defined | `UserDefinedFileAttributeView` | Extended attributes if provider supports them |

Libraries can query support at two levels:

```java
Set<String> providerViews =
        path.getFileSystem().supportedFileAttributeViews();

FileStore store = Files.getFileStore(path);
boolean posixAvailable =
        store.supportsFileAttributeView(
                PosixFileAttributeView.class);
```

This snippet requires importing `Set`, `FileStore`, `PosixFileAttributeView`, and `Path`; `Files.getFileStore` can throw `IOException`.

- `supportedFileAttributeViews()` reflects capabilities of the **filesystem provider** in general.
- `FileStore.supportsFileAttributeView(...)` queries a specific **file store**.
- Runtime permissions can still cause attribute reads/updates to fail even when the view is supported.
- Never rely solely on `System.getProperty("os.name")`: a single OS can mount multiple file stores with different capabilities.

`Files.getFileAttributeView(path, PosixFileAttributeView.class)` can return `null` when unsupported. Calling `Files.getPosixFilePermissions` on a filesystem without POSIX support typically throws `UnsupportedOperationException`. Tests must include a dedicated skip branch.

## 10. Complete Java 17+ Example: Checking File Store Capabilities

Create **`FileAttributeCapabilityDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.AclFileAttributeView;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.DosFileAttributeView;
import java.nio.file.attribute.PosixFileAttributeView;
import java.util.Set;

public class FileAttributeCapabilityDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("nio-views-");
        Path file = dir.resolve("sample.txt");

        try {
            Files.writeString(file, "hello");

            Set<String> views =
                    file.getFileSystem().supportedFileAttributeViews();
            FileStore store = Files.getFileStore(file);

            boolean basic = Files.getFileAttributeView(
                    file, BasicFileAttributeView.class) != null;
            boolean posix = store.supportsFileAttributeView(
                    PosixFileAttributeView.class);
            boolean dos = store.supportsFileAttributeView(
                    DosFileAttributeView.class);
            boolean acl = store.supportsFileAttributeView(
                    AclFileAttributeView.class);

            System.out.println("basic=" + basic);
            System.out.println("providerSupportsBasic="
                    + views.contains("basic"));
            System.out.println("posixSupported=" + posix);
            System.out.println("dosSupported=" + dos);
            System.out.println("aclSupported=" + acl);

            // Probe results do not replace actual open/read/write.
            System.out.println("content="
                    + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 FileAttributeCapabilityDemo.java
java FileAttributeCapabilityDemo
```

Two lines are guaranteed under standard filesystem provider contracts when operations succeed:

```text
basic=true
providerSupportsBasic=true
```

The remaining lines **depend on the platform and file store**:

```text
posixSupported=<true or false>
dosSupported=<true or false>
aclSupported=<true or false>
content=hello
```

The `<true or false>` markers are **capability descriptions**, not literal character-by-character output. The real program prints `true` or `false`. Never write unit tests requiring POSIX to be `true` or DOS/ACL to be `false`: Java can run on filesystems with different capabilities from the host OS.

**Explanation:** `getFileStore(file)` inspects the test file's store rather than guessing from the OS. `supportsFileAttributeView` reports a capability, **not** that the process always has permission to modify those attributes. The example alters no real user owners, ACLs, or permissions, so it runs safely in a temporary workspace without affecting user file settings.

## 11. POSIX Permissions: Understanding Bits and Limits

On a file store supporting POSIX, permissions can be read with:

```java
Set<PosixFilePermission> perms =
        Files.getPosixFilePermissions(path);
String symbolic = PosixFilePermissions.toString(perms);
```

This snippet requires `path`, imports for `Set`, `PosixFilePermission`, `PosixFilePermissions`, and handling `IOException`/`UnsupportedOperationException`.

Notation like `rwxr-x---` represents read/write/execute permissions for **owner, group, others**. Effective access can still depend on the current user, supplementary groups, ACLs, mount flags, parent directory permissions, and OS rules.

Notes:

- On filesystems without a POSIX view, calling `getPosixFilePermissions` can fail with `UnsupportedOperationException`.
- `Files.setPosixFilePermissions(path, perms)` **mutates real file permissions**; never run it on user files in test examples.
- `Files.createTempFile`/`createTempDirectory` may assign different initial permissions depending on provider and `umask`; never hardcode expected octal output across all machines.
- POSIX `OWNER_READ` is not equivalent to "every process can read."
- On Windows, NTFS permissions rely primarily on ACLs; access rules cannot be inferred solely from an `rwx` model.
- Never use OS permission bits as web-user business authorization. Enforce application-level authorization separately.

### Non-Mutating Permission Probing

In diagnostics, logging **non-sensitive** details like `posixSupported=true`, `fileType=regular`, and `testReadSucceeded=true` can be helpful. If owner/group/path must be logged, evaluate access controls and data protection; owners or paths can contain real usernames.

`Files.isWritable(path)` returning `true` **does not promise** `Files.write(path, bytes)` will succeed later: the system can hit disk full, quotas, file locks, state changes, or policy denials at write time.

## 12. DOS Flags and ACLs: Not Identical to POSIX

**DOS attributes** such as `readonly`, `hidden`, `archive`, and `system` are accessed via `DosFileAttributeView` when supported by the provider. They are not direct equivalents of POSIX bits.

**ACLs** via `AclFileAttributeView` represent a list of allow/deny entries. Systems may evaluate ACE order and type, user/group principals, and inheritance rules; **do not** build a naive parser and claim "this user can definitely read."

Example view detection:

```java
AclFileAttributeView aclView = Files.getFileAttributeView(
        path, AclFileAttributeView.class);

if (aclView == null) {
    // No ACL view for this path/provider.
} else {
    // Only when business logic requires it and permissions allow,
    // read ACL according to security policy.
}
```

This is a snippet. `getAcl()` can return sensitive user/group details; never print full ACLs on public error pages. For tests modifying ACLs or owners, use an isolated environment under explicit policy and restore/clean up state afterward; never alter ACLs on shared working directories.

## 13. Trying the Real Operation and Catching Errors Properly

Necessary probes should prefer **the minimal operation the business logic intends**, within an authorized file/directory scope:

```java
try (var in = Files.newInputStream(path)) {
    byte[] first = in.readNBytes(32);
    // Process only the first.length bytes actually read.
} catch (java.nio.file.NoSuchFileException ex) {
    // Does not exist at open time.
} catch (java.nio.file.AccessDeniedException ex) {
    // System denied access.
} catch (IOException ex) {
    // Other I/O errors.
}
```

This snippet requires `IOException`, `Files`, `Path`, and an authorized `path` from the business flow. If you must refuse to follow a final symbolic link, **open using an API with the appropriate option contract**, rather than calling `isSymbolicLink` and then opening normally.

One option on providers supporting `NOFOLLOW_LINKS` when opening a channel:

```java
try (var channel = Files.newByteChannel(
        path,
        java.util.Set.of(
                java.nio.file.StandardOpenOption.READ,
                LinkOption.NOFOLLOW_LINKS))) {
    // Read from the opened channel if successful.
}
```

This snippet assumes `path`, imports for `Files` and `LinkOption`, and handling for `IOException`/`UnsupportedOperationException`. `NOFOLLOW_LINKS` is a supported `OpenOption` under appropriate NIO contracts; when the final target is a symbolic link, opening fails instead of following the link. It **does not by itself prevent parent path components from containing symlinks** or an adversary swapping paths before opening.

Think in terms of **opening the concrete object once and operating on the opened handle**, minimizing "check path → reuse path" sequences that create race windows.

## 14. TOCTOU: Bugs Between Check and Use

TOCTOU (*Time Of Check To Time Of Use*) happens when state is checked at one moment, yet the file changes before the subsequent operation.

Unsafe example:

```java
Path candidate = root.resolve(userSuppliedName).normalize();

if (candidate.startsWith(root)
        && !Files.isSymbolicLink(candidate)
        && Files.isReadable(candidate)) {
    // Another process may replace candidate after the checks.
    return Files.readAllBytes(candidate);
}
```

This snippet intentionally illustrates risk; `root` and `userSuppliedName` must be declared with input validation and exception handling. Beyond the final-symlink race, `candidate.startsWith(root)` checks **syntactically normalized paths** and does not guarantee the real path stays inside `root` if a parent directory contains a symlink.

Mitigations according to risk level:

1. **Do not let clients supply arbitrary paths**; map resource IDs to server-managed storage keys.
2. Configure storage directories with proper OS permissions so untrusted parties cannot alter entries or symlinks.
3. Use `NOFOLLOW_LINKS` open options when forbidding final symlinks; also evaluate every path segment.
4. On supporting providers, consider `SecureDirectoryStream` to perform relative operations through a directory handle and reduce races during entry resolution.
5. For newly created files, use `StandardOpenOption.CREATE_NEW` to avoid overwriting existing entries where appropriate; combine with directory permissions and relevant options.
6. Handle `IOException` directly on the real operation; never treat a pre-check as a guaranteed license.
7. Where high security is needed, verify identity/file identity and permissions on the OS/resource handle as supported by the environment, rather than relying on string paths.

`Path.toRealPath()` resolves the real path per contract, yet that result **can also become stale immediately after the call**. Never treat path canonicalization as complete protection against symlink swaps.

## 15. `toRealPath()` and Canonical Paths: Using Them with Accurate Meaning

Comparison:

| API | Primary Effect |
| --- | --- |
| `path.toAbsolutePath()` | Produces an absolute form using filesystem context |
| `path.normalize()` | Syntactically collapses `.` and `..`; need not access the real file |
| `path.toRealPath()` | Returns the real path of an existing entry, following links by default, resolved per provider |
| `path.toRealPath(NOFOLLOW_LINKS)` | Returns the real path opting not to follow symbolic links per contract |
| `Files.readSymbolicLink(path)` | Returns the target stored in the symlink, which may be relative and non-existent |

`toRealPath()` can throw `NoSuchFileException`, `FileSystemLoopException`, or `IOException` if unresolvable. `normalize()` does not verify file existence. Platform specifics also affect case sensitivity and aliasing.

Never print `toRealPath()` (or internal root paths) in an HTTP error response just for diagnostics; it can leak usernames, mounts, or deployment layout. Return stable public error codes and store diagnostics under proper access policies.

## 16. Directory Tree Traversal and Symbolic Link Loops

`Files.walkFileTree(start, visitor)` **does not follow symlinks** by default. Passing `FileVisitOption.FOLLOW_LINKS` lets traversal enter linked directories and potentially hit cycles.

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(
                java.nio.file.FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
```

This snippet requires `root`, a `FileVisitor<Path> visitor`, and imports; it is not standalone. With `FOLLOW_LINKS`, Java performs cycle detection; `FileSystemLoopException` can be delivered to `visitFileFailed`. The visitor author must decide how to handle it.

When **there is no need to follow links**, keep the default no-follow behavior and handle symbolic-link entries explicitly if needed. Especially when deleting or archiving directory trees, a traversal following links outside the root can touch out-of-scope data. Never run a "directory cleanup" on untrusted paths with `FOLLOW_LINKS` without strictly bounding its effects.

### Do Not Treat Every Directory Listing as a Snapshot

`Files.walk` or `walkFileTree` can observe mutations while traversing. Deleted entries, changed permissions, or swapped links can fail a walk mid-way. Diagnostics must handle exceptions per entry and never assume the returned listing is an atomic snapshot.

## 17. Windows, Linux, macOS, and Provider Specifics

| Topic | What Can Vary |
| --- | --- |
| Symlink creation capability | Filesystem, OS privileges, policy, Windows Developer Mode / privileges |
| POSIX permission bits | Common on Unix-like filesystems; do not assume present on Windows/NTFS |
| ACLs | Present on Windows/NTFS and some other filesystems; not identical to POSIX bits |
| DOS attributes | Tied to FAT/NTFS or related providers; absent on some stores |
| Case sensitivity | NTFS, APFS, ext4, etc., differ in configuration and semantics |
| Separator / path syntax | Windows/Unix and filesystem providers represent paths differently |
| Symlink / junction / reparse point | Certain OS-specific links do not always report uniformly through the same API |
| Deleting open files | Sharing/locking semantics differ sharply between Windows and POSIX |
| Atomic rename | Depends on file store/provider and `ATOMIC_MOVE` support |
| Timestamp precision | Timestamps may be rounded or updated under different rules |
| Network filesystems | Caching, credentials, network errors, eventual visibility, remote permissions |
| Virtual filesystems | ZIP filesystems, in-memory providers, and read-only stores support different operation sets |

Never use `System.getProperty("os.name")` to hardcode all behavior. Inspect **specific capabilities** on the path/file store and **try real operations** when permitted. One OS can mount multiple stores with different capabilities, or the same store can change policy between CI and production.

## 18. Writing Portable Tests Instead of Single-Machine Tests

A solid test:

- Creates files and directories **strictly inside a test-owned temp directory**.
- For optional features like symlinks or POSIX views, uses an explicit **skip/assumption** branch when unsupported or unauthorized.
- Distinguishes **unsupported** from **supported yet unexpectedly failing**; never catches every exception indiscriminately and reports PASS.
- Never demands exact POSIX permission strings or ACLs across all platforms.
- Never mutates permissions or ownership on existing user files or shared CI directories.
- After creating a link, verifies it with specific APIs such as `readAttributes(..., NOFOLLOW_LINKS)`.
- Tests broken links, relative links, target survival/permissions, and cleanup.
- Does not rely on identical listing order or timestamp precision across every filesystem.
- When testing security-critical code, adds tests with concurrent symlink swaps or controlled environments, explicitly noting race non-determinism.

### Complete Java 17+ Example: Conditionally Testing Symlink Support

Create **`SymlinkInvariantTest.java`**:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class SymlinkInvariantTest {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("symlink-test-");
        Path target = dir.resolve("data.txt");
        Path link = dir.resolve("alias.txt");

        try {
            Files.writeString(target, "OK");

            try {
                Files.createSymbolicLink(link, Path.of("data.txt"));
            } catch (UnsupportedOperationException
                     | IOException | SecurityException ex) {
                System.out.println("SKIP: symlink cannot be created");
                return;
            }

            BasicFileAttributes attrs = Files.readAttributes(
                    link, BasicFileAttributes.class,
                    LinkOption.NOFOLLOW_LINKS);

            if (!attrs.isSymbolicLink()) {
                throw new AssertionError("Expected symbolic link");
            }
            if (!Files.isSameFile(link, target)) {
                throw new AssertionError("Link must resolve to target");
            }
            if (!Files.readString(link).equals("OK")) {
                throw new AssertionError("Following link read wrong data");
            }

            Files.delete(link);
            if (!Files.exists(target)) {
                throw new AssertionError("Target must survive link deletion");
            }

            System.out.println("PASS: symlink invariants");
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac -encoding UTF-8 SymlinkInvariantTest.java
java SymlinkInvariantTest
```

Output if symlinks are supported and all checks pass:

```text
PASS: symlink invariants
```

If provider/policy prevents link creation:

```text
SKIP: symlink cannot be created
```

**How this differs from an "always PASS" test**: if link creation succeeds yet `readAttributes`, `isSameFile`, or `readString` fails unexpectedly, the error is not swallowed by the link-creation `catch`. If data is wrong, `AssertionError` fails the test. Skipping is strictly scoped to the optional link-creation step.

In larger test suites, classify the skip reason (unsupported/permission/other I/O) to help operations diagnose issues; this minimal example prints a single generic message and avoids JUnit dependencies.

## 19. Diagnosing Permission Errors Without Leaking Internal Details

When an I/O action is denied, operational logs may need:

```text
event=FILE_ACCESS_FAILED
operation=OPEN_READ
reason=ACCESS_DENIED
requestId=<server-generated-id>
```

Never automatically return to clients or log publicly:

```text
AccessDeniedException:
 /var/run/secrets/app/production/token.key
```

`AccessDeniedException.getFile()`, `FileSystemException.getReason()`, or `exception.getMessage()` can expose paths and provider details. If full diagnostics are needed, route them to protected channels with policy-controlled retention and content; **public responses** only need stable error codes.

Security tests for public error messages should intentionally use paths containing sensitive sentinel strings and verify that responses/serializers never echo them. Distinguish process-level file access errors from **user-level business authorization**; both layers can yield HTTP 403/404/500 depending on API policy.

## 20. Misconceptions to Avoid

1. **"`Files.exists` returning `false` guarantees the file does not exist."** False: access errors can render it indeterminate.
2. **"A broken link means no directory entry exists."** False: `NOFOLLOW_LINKS` can prove the link entry still exists.
3. **"`Files.isSymbolicLink` returning `false` proves the file is not a symlink."** Not necessarily if an I/O error prevented determining the type.
4. **"`NOFOLLOW_LINKS` blocks symlinks in all parent directories."** Insufficient: understand API contracts and directory/path security design.
5. **"`readSymbolicLink` always returns an absolute path."** It can return the relative target stored in the link.
6. **"Deleting a symbolic link deletes the target too."** False for `Files.delete(link)` under normal rules.
7. **"A hard link is just a symlink by another name."** False; file identity and content linkage have different semantics.
8. **"`isReadable` returning `true` means reading will definitely succeed."** False: TOCTOU and other factors can still fail I/O.
9. **"`isWritable` returning `false` is always an ACL denial."** False: it can mean indeterminate status or another policy.
10. **"Every OS supports POSIX permissions."** False; inspect the file store's views.
11. **"Windows can never create symlinks."** False; depends on OS version, privileges, and provider.
12. **"Every file store on Linux is identical."** False; network, ZIP, FUSE, and container stores vary.
13. **"`normalize` and `toRealPath` alone prevent path traversal."** False if symlink races or authorization gaps remain.
14. **"Having an ACL view means the web user is authorized."** False; OS permissions differ from application policy.
15. **"`Files.walkFileTree` follows links by default."** False; you must explicitly pass `FOLLOW_LINKS`.
16. **"Symlink cycles are always ignored silently."** False; following links can throw `FileSystemLoopException`.
17. **"Timestamps and traversal order are always identical across Windows/macOS/Linux."** False; write contract-based tests.
18. **"A test failing to create a symlink means symlink-handling code is buggy."** Not necessarily; the feature may be unsupported or blocked by policy.
19. **"Catch every `IOException` and report SKIP."** False: hides real bugs once the feature is known to be supported.
20. **"Printing raw paths for debugging is harmless."** It can leak usernames, server layouts, and private storage keys.

## 21. Practice Exercises

### Exercise A — Broken Link

Create a symlink `broken.txt -> missing.txt` in a temporary directory. Predict `exists` with/without `NOFOLLOW_LINKS`, `isSymbolicLink`, and `readSymbolicLink`. Why can the results differ?

### Exercise B — POSIX/ACL Capabilities

On your machine, use `Files.getFileStore(path)`, `supportsFileAttributeView(PosixFileAttributeView.class)`, and `AclFileAttributeView.class`. Compare two different file stores if available. Why shouldn't one result be generalized into an OS-wide rule?

### Exercise C — Race Between Check and Operation

One process calls `Files.isRegularFile(candidate, NOFOLLOW_LINKS)`, and another process swaps the entry for a symbolic link before `Files.readString(candidate)`. Explain the TOCTOU risk and propose mitigations using directory restrictions, open options, and handles.

### Exercise D — Directory Traversal

A ZIP file contains an entry `../../outside.txt`. Why is `root.resolve(name).normalize().startsWith(root)` still insufficient if a directory inside `root` can be replaced with a symlink? When operating on a directory tree modified concurrently by another user, what provider capabilities should you consider?

### Exercise E — Portable CI Tests

Modify `SymlinkInvariantTest` to log the skip reason to an internal channel without printing paths to public output. In an environment that does not support symlinks, why skip symlink-property tests instead of failing the entire build (if the feature is optional)?

### Exercise F — Open Files and Cleanup

Try opening a `FileChannel`, then deleting or renaming the file in the same process on different OSes. Record actual behavior without writing portable tests that assume Windows and POSIX behave identically. Close the channel and delete temporary data safely afterward.

## 22. Self-Check Questions

1. How does `Files.isSymbolicLink(path)` differ from `Files.isRegularFile(path, NOFOLLOW_LINKS)`?
2. When a symlink's target is deleted, why can `Files.exists(link)` and `Files.exists(link, NOFOLLOW_LINKS)` differ?
3. What is the relative `Path` returned by `Files.readSymbolicLink(link)` relative to?
4. What is the meaning and limitation of `NOFOLLOW_LINKS` in defending against symlink attacks?
5. When should you use `Files.readAttributes(..., NOFOLLOW_LINKS)` instead of `Files.isSymbolicLink` alone?
6. Does `Files.isReadable(path)` returning `true` replace catching `IOException`?
7. What does `FileStore.supportsFileAttributeView` tell you, and what does it not promise?
8. Can POSIX permissions and Windows ACLs be completely unified?
9. Why can checking permissions before opening a file create a TOCTOU vulnerability?
10. Does `Files.delete(link)` automatically delete the symlink target's contents?
11. Why is `Path.normalize()` not a reliable security root check?
12. When using `FOLLOW_LINKS` in `walkFileTree`, what kind of error must you account for?
13. If CI cannot create symlinks, how should tests be structured so real bugs in other features are still caught?
14. Why should tests run across multiple file store types rather than just multiple OS names?
15. Should you display absolute paths or owner names on an HTTP error page when `AccessDeniedException` occurs?

## 23. Java 17 Reference Documentation

- [`Files` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): creating/reading symbolic links, `exists`, `readAttributes`, access probes, `walkFileTree`.
- [`Path` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `normalize`, `toAbsolutePath`, `toRealPath`, and provider semantics.
- [`LinkOption` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [`FileStore` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): `supportsFileAttributeView`.
- [`java.nio.file.attribute` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/package-summary.html): Basic/POSIX/DOS/ACL/User-defined attribute views.
- [`SecureDirectoryStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): directory-entry operations reducing races where supported by the provider.
- [`FileVisitOption` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` during tree traversal.

## 24. Takeaways

**A symbolic link is a distinct entry pointing to a target**, and `NOFOLLOW_LINKS` applies only to APIs that honor it. For a broken link, a default existence check can return `false` while checking the link itself with `NOFOLLOW_LINKS` returns `true`.

**Access permissions and file attributes depend on the provider/file store, OS, process identity, and timing.** `Files.isReadable`/`isWritable` do not replace actually opening the file; POSIX/DOS/ACL views must be probed dynamically. For security-sensitive code, avoid TOCTOU by controlling roots and handles, setting proper directory permissions, using non-following open options, and validating path components—not relying on `normalize()` alone.

High-quality tests **use only temporary resources**, recognize optional capabilities, distinguish SKIP from FAIL, never demand identical permission/symlink outputs on every platform, and never leak internal paths in public messages.
