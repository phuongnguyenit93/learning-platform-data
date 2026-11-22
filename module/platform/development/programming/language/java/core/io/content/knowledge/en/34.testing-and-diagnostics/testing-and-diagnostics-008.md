# Checking Symbolic Links, Permissions, and Platform-Specific Behavior in Java NIO.2

## 1. Lesson Objectives

I/O code that passes on Linux can fail on Windows, macOS, network filesystems, USB drives, or virtual filesystems. The culprits often involve **symbolic links**, **file permissions**, **file attribute views**, provider policies, and changes occurring between checking a path and using it.

For example, the following code is not a safety guarantee:

```java
if (Files.exists(path) && Files.isReadable(path)) {
    // Does not guarantee the subsequent read will succeed.
    String content = Files.readString(path);
}
```

This is a snippet, not a standalone program. After the check, the file may be deleted, have its permissions changed, be renamed, replaced with a symbolic link, or locked by another mechanism; `readString` can still throw `IOException`.

After this lesson, you will be able to:

1. Check whether a `Path` is a symbolic link, read its link target, and distinguish **following links** from **`NOFOLLOW_LINKS`**.
2. Explain why a broken link can yield `Files.exists(path) == false` while `Files.exists(path, NOFOLLOW_LINKS) == true`.
3. Inspect basic attributes and detect support for **POSIX permissions**, **DOS attributes**, or **ACLs** without assuming every platform supports them.
4. Distinguish `Files.isReadable/isWritable/isExecutable` from reliable access checks; understand **TOCTOU** race conditions.
5. Write Java 17+ examples and tests whose **platform-dependent outcomes are clearly identified**, rather than treating Linux results as universal.
6. Handle unsupported operations, missing permissions, symbolic-link loops, temporary paths, and safe cleanup.

In **Testing and Diagnostics**, the focus is knowing how to **observe, verify, and draw accurately scoped conclusions**, not trying to bypass OS permissions.

## 2. What Is a Symbolic Link?

A symbolic link (*symlink*) is a filesystem entry containing a reference to a target path. It is **not** a copy of the target file's contents and is not the same as a **hard link**.

```text
work/
  actual.txt       content: "HELLO"
  shortcut.txt -->  actual.txt      (relative symbolic link)
```

When a program accesses `shortcut.txt`, many `Files` operations **follow the symlink** to `actual.txt` by default; certain operations are designed to inspect the link object itself.

Distinguish:

- **Link path**: the path where the symbolic link lives, e.g., `work/shortcut.txt`.
- **Link target**: the target value stored inside the link, e.g., `actual.txt` or an absolute path.
- **Resolved target**: the path obtained when the system resolves a relative target against the **directory containing the link**, not by default the Java process's working directory.
- **Dangling/broken link**: the link entry exists, yet its target does not exist or cannot be resolved.
- **Link cycle**: a chain of links or directory link forming a loop when traversed.

For example, `Files.readSymbolicLink(link)` returns the target stored in the link and **does not necessarily return an absolute path**. If the target is relative, its resolution context is the link's parent directory.

## 3. Key Methods and Options

| API | Purpose | Notes |
| --- | --- | --- |
| `Files.isSymbolicLink(path)` | Checks if an entry is a symbolic link | May return `false` if indeterminable |
| `Files.createSymbolicLink(link, target)` | Creates a symlink; depends on provider/OS support | May be unsupported or lack permissions |
| `Files.readSymbolicLink(link)` | Reads the target stored in the link | Target may be relative or non-existent |
| `Files.exists(path)` | Checks if path exists following links by default | Returns `false` if indeterminable or link target is missing |
| `Files.exists(path, NOFOLLOW_LINKS)` | Checks the link entry itself without following target | May be `true` even when target is missing |
| `Files.isRegularFile(path, NOFOLLOW_LINKS)` | Checks the type of the entry itself | A symlink is not considered a regular file |
| `Files.readAttributes(path, BasicFileAttributes.class, options)` | Reads type, size, timestamps, file key | Can throw `IOException`; useful for distinguishing errors |
| `Path.toRealPath(options)` | Returns the real path per provider contract | Not a standalone authorization mechanism |
| `Files.isSameFile(a, b)` | Checks if two paths locate the same file | Can access the filesystem and throw `IOException` |
| `Files.delete(link)` | Deletes the specified directory entry | Deleting a symlink does not delete its target |
| `Files.walkFileTree(...)` | Traverses a directory tree | Does not follow symlinks by default; `FOLLOW_LINKS` has specific effects |

Common imports:

```java
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
```

These imports support the snippets in this lesson. When catching errors, use `IOException` and its subclasses or `UnsupportedOperationException` per API behavior.

## 4. What Does `NOFOLLOW_LINKS` Mean Exactly?

`LinkOption.NOFOLLOW_LINKS` controls whether symbolic links are followed for **APIs accepting `LinkOption...` or honoring this option per contract**.

Suppose:

```text
dir/
  item.txt
  link.txt -> item.txt
  broken.txt -> missing.txt
```

On a system supporting symlinks in an intact state:

| Check | `item.txt` | `link.txt` | `broken.txt` |
| --- | --- | --- | --- |
| `Files.exists(path)` | true | true | false |
| `Files.exists(path, NOFOLLOW_LINKS)` | true | true | true |
| `Files.isSymbolicLink(path)` | false | true | true |
| `Files.isRegularFile(path)` | true | true | false |
| `Files.isRegularFile(path, NOFOLLOW_LINKS)` | true | false | false |
| `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS).isSymbolicLink()` | false | true | true |

The table describes **normal local files with permissions and proper provider classification**; it does not promise `Files.exists` returns those values under I/O errors or insufficient permissions.

**Two warnings:**

1. Not every `Files` method accepts or honors `NOFOLLOW_LINKS` identically; read the specific method's Javadoc.
2. `NOFOLLOW_LINKS` generally controls following the **final symbolic link** for the invoked API; it **does not automatically guarantee that no parent directory component contains a symlink or changes mid-operation**.

If a security requirement is "must never escape the root directory even with symlinks in the path", checking only `normalize()` or `exists(..., NOFOLLOW_LINKS)` is insufficient.

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

                Files.delete(link); // deletes link, not actual
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

Compile/run:

```bash
javac -encoding UTF-8 SymbolicLinkInspectionDemo.java
java SymbolicLinkInspectionDemo
```

**Stdout when the platform supports symlink creation and I/O operations succeed:**

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

and the program skips symlink checks. Seeing `false` alone does not prove "Windows does not support symlinks": the cause may be permissions, filesystem, policy, provider, or I/O conditions. Never write tests requiring symlink creation to succeed on every CI runner.

**Explanation:**

- `createSymbolicLink(link, Path.of("actual.txt"))` creates a relative target: the path is resolved from the **directory containing `shortcut.txt`**.
- `readSymbolicLink(link).isAbsolute()` is `false` because the stored target is relative.
- Without `NOFOLLOW_LINKS`, `isRegularFile(link)` inspects target `actual.txt`; with `NOFOLLOW_LINKS`, it inspects the link entry itself.
- `BasicFileAttributes` checks file type with explicit I/O error reporting.
- `broken.txt` has a symlink entry while target `missing.txt` does not exist, so the two `exists` calls differ.
- `Files.delete(link)` does not delete `actual.txt`.
- Cleanup deletes each created entry; the example touches nothing outside its own temporary directory.

The `catch` around link creation only handles platform capability errors to **skip link checks**. Subsequent I/O operations can still fail; the example lets those exceptions surface as test failures rather than masking all errors with `catch (Exception)`.

## 6. Do Not Confuse Symlinks with Hard Links or Desktop Shortcuts

A **hard link** is another directory entry pointing to the same file object, created with `Files.createLink(link, existing)` if supported by the provider/filesystem. It is generally not reported as a symbolic link by `Files.isSymbolicLink()`.

| Characteristic | Symbolic Link | Hard Link |
| --- | --- | --- |
| Can target be non-existent? | Yes | Usually must point to an existing file |
| `Files.isSymbolicLink` | `true` for recognized valid symlinks | `false` |
| `Files.readSymbolicLink` | Reads stored target string | Not applicable |
| Deleting one entry | Deletes link; leaves target intact | Removes one directory entry; data may persist via another hard link |
| Supportability | May be restricted by OS/policy/provider | Varies by filesystem/provider |
| Testing impact | Test follow/`NOFOLLOW` | Test file identity and link count per OS when appropriate |

Windows `.lnk` shortcut files are typically **shell-handled files**, not filesystem symbolic links recognized by `Files.isSymbolicLink`. Likewise, GUI aliases and junctions/reparse points have platform-specific semantics; do not assume every link type behaves uniformly through `java.nio.file.Files`.

## 7. Permissions in Java: Probing Differs from Actually Opening

Convenience probes:

```java
boolean readable = Files.isReadable(path);
boolean writable = Files.isWritable(path);
boolean executable = Files.isExecutable(path);
```

This snippet requires `path`. These methods are useful for **displaying observed status** or fast-path hints, yet:

- Returning `true` does not promise a subsequent `Files.newInputStream`/`newOutputStream` will succeed.
- Returning `false` may mean missing permissions **or inability to determine** permissions at that instant.
- Actual access may involve owner, group, ACLs, sandbox policies, share modes, network mounts, or process identity.
- The file's permissions, existence, or link target can change between probe and operation.
- `isWritable == true` does not guarantee available disk quota/space or healthy storage.

The right approach is to **perform the needed I/O operation and catch resulting exceptions**, instead of using `isReadable` as a user "authorization check".

Example:

```java
try (var in = Files.newInputStream(path)) {
    // Process content and verify I/O results.
} catch (java.nio.file.NoSuchFileException ex) {
    // File/path did not exist at operation time.
} catch (java.nio.file.AccessDeniedException ex) {
    // OS/provider denied access.
} catch (java.io.IOException ex) {
    // Other I/O errors: link loop, device, filesystem...
}
```

This is a snippet, not a standalone program. Specific exception subclasses do not appear identically across all providers; many failures arrive as `FileSystemException` or generic `IOException`. **Never treat `AccessDeniedException` as a substitute for business authorization**; the OS and application have separate permission models.

## 8. Basic Attributes Are the Portable Starting Point

`BasicFileAttributes` exposes fundamental properties:

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
- Timestamps share the same granularity or update policies across OSes.
- `fileKey()` is always non-null, permanently stable, or safe as a public ID.
- A symlink's `size()` under `NOFOLLOW_LINKS` equals the target's byte size.
- All attributes are read atomically against concurrent modifications: Javadoc allows provider differences.

When you must distinguish "not a symbolic link" from "indeterminable due to I/O error", use `readAttributes(..., NOFOLLOW_LINKS)` and handle exceptions rather than calling `Files.isSymbolicLink` alone and treating `false` as absolute proof.

## 9. Platform-Specific Attribute View Groups

Java NIO.2 defines several attribute view interfaces, whose concrete support depends on filesystem/provider:

| View | Java API | Typical Information |
| --- | --- | --- |
| Basic | `BasicFileAttributeView` | Entry type, size, timestamps, file key |
| POSIX | `PosixFileAttributeView` | Owner, group, POSIX permission bits |
| DOS | `DosFileAttributeView` | Readonly, hidden, archive, system flags |
| Owner | `FileOwnerAttributeView` | Owner user principal |
| ACL | `AclFileAttributeView` | ACE list and owner |
| User-defined | `UserDefinedFileAttributeView` | Extended attributes if supported by provider |

Libraries can query support at two levels:

```java
Set<String> providerViews =
        path.getFileSystem().supportedFileAttributeViews();

FileStore store = Files.getFileStore(path);
boolean posixAvailable =
        store.supportsFileAttributeView(
                PosixFileAttributeView.class);
```

This snippet requires imports for `Set`, `FileStore`, `PosixFileAttributeView`, and `Path`; `Files.getFileStore` can throw `IOException`.

- `supportedFileAttributeViews()` reflects what the **filesystem provider** supports generally.
- `FileStore.supportsFileAttributeView(...)` queries support on a specific **file store**.
- Actual permissions can still cause reading/modifying attributes to fail even when the view is supported.
- Never use `System.getProperty("os.name")` as the sole decision source: even one OS can mount multiple file stores with differing capabilities.

`Files.getFileAttributeView(path, PosixFileAttributeView.class)` can return `null` when unsupported. Calling `Files.getPosixFilePermissions` on a non-POSIX filesystem typically throws `UnsupportedOperationException`. Tests must include explicit skip branches.

## 10. Complete Java 17+ Example: Probing File Store Capabilities

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

            // Probing results do not replace actual open/read/write.
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

Two lines guaranteed under standard filesystem provider contracts when operations succeed:

```text
basic=true
providerSupportsBasic=true
```

Subsequent lines **depend on the platform and file store**:

```text
posixSupported=<true or false>
dosSupported=<true or false>
aclSupported=<true or false>
content=hello
```

The `<true or false>` placeholders are **capability descriptions**, not literal character-for-character expected output. The actual program prints `true` or `false`. Never write unit tests forcing POSIX to be `true` or DOS/ACL to be `false`: Java may run on filesystems with different capabilities than the host OS.

**Explanation:** `getFileStore(file)` inspects the test file's store rather than inferring from the OS. `supportsFileAttributeView` reports capability, **not** that the process always has permission to modify those attributes. The example does not alter real owners/ACLs or permissions, so it runs safely inside a temporary workspace without affecting user file settings.

## 11. POSIX Permissions: Understanding Bits and Limits

On file stores supporting POSIX, permissions can be read via:

```java
Set<PosixFilePermission> perms =
        Files.getPosixFilePermissions(path);
String symbolic = PosixFilePermissions.toString(perms);
```

This snippet requires `path`, imports for `Set`, `PosixFilePermission`, `PosixFilePermissions`, and handling for `IOException`/`UnsupportedOperationException`.

Notation like `rwxr-x---` shows read/write/execute permissions for **owner, group, others**. Yet effective access can also depend on current user, supplementary groups, ACLs, mount flags, parent directory permissions, and OS rules.

Notes:

- On filesystems without a POSIX view, calling `getPosixFilePermissions` can fail with `UnsupportedOperationException`.
- `Files.setPosixFilePermissions(path, perms)` **modifies real file permissions**; never run it on user files in test demos.
- `Files.createTempFile`/`createTempDirectory` may create different initial permissions depending on provider and `umask`; never hardcode expected octal outputs across all machines.
- POSIX `OWNER_READ` does not mean "any process can read".
- On Windows, NTFS permissions rely primarily on ACLs; access rules cannot be deduced from an `rwx` diagram.
- Never use permission bits as a business authorization check for web users. Implement separate application-level authorization.

### Non-mutating permission diagnostics

In diagnostics, logging **non-sensitive** details like `posixSupported=true`, `fileType=regular`, `testReadSucceeded=true` can be helpful. If logging owner/group/path, assess access controls and data protection; owners or paths can expose real usernames.

A `Files.isWritable(path)` check returning `true` **does not promise** `Files.write(path, bytes)` will succeed later: the system may run out of disk space, hit quotas, encounter file locks, change state, or reject writes by policy at execution time.

## 12. DOS Flags and ACLs: Not Identical to POSIX

**DOS attributes** such as `readonly`, `hidden`, `archive`, and `system` are accessible via `DosFileAttributeView` if supported by the provider. They are not direct equivalents of POSIX bits.

**ACLs** via `AclFileAttributeView` represent ordered lists of allow/deny entries. Systems may evaluate ACE order and types, user/group principals, and custom inheritance rules; **never** build a naive parser and claim "this user can definitely read".

View detection example:

```java
AclFileAttributeView aclView = Files.getFileAttributeView(
        path, AclFileAttributeView.class);

if (aclView == null) {
    // No ACL view for this path/provider.
} else {
    // Only when required by business logic and permitted,
    // read ACLs per security policy.
}
```

This is a snippet. `getAcl()` can return sensitive user/group data; never dump full ACLs on public error pages. For tests modifying ACLs/owners, use an isolated environment with explicit policies and restore/clean up state afterward; never alter ACLs on shared working directories.

## 13. Perform the Real Operation and Handle Errors Properly

Essential probing should favor the **minimal operation the business flow intends to perform**, within authorized files/directories:

```java
try (var in = Files.newInputStream(path)) {
    byte[] first = in.readNBytes(32);
    // Process only first.length bytes actually read.
} catch (java.nio.file.NoSuchFileException ex) {
    // Did not exist at open time.
} catch (java.nio.file.AccessDeniedException ex) {
    // System denied access.
} catch (IOException ex) {
    // Other IO errors.
}
```

This snippet requires `IOException`, `Files`, `Path`, and a `path` from an authorized business flow. If you must avoid following a final symbolic link, **open using an API with the appropriate option contract**, rather than checking `isSymbolicLink` and then opening normally.

One option for providers supporting `NOFOLLOW_LINKS` when opening a channel is:

```java
try (var channel = Files.newByteChannel(
        path,
        java.util.Set.of(
                java.nio.file.StandardOpenOption.READ,
                LinkOption.NOFOLLOW_LINKS))) {
    // Read from the opened channel if open succeeds.
}
```

This snippet assumes `path`, imports `Files` and `LinkOption`, and handles `IOException`/`UnsupportedOperationException`. `NOFOLLOW_LINKS` is an `OpenOption` supported under compatible NIO contracts; when the final target is a symbolic link, opening fails instead of following the link. It **does not automatically prevent parent directories from containing symlinks** or an adversary from swapping paths prior to opening.

Think in terms of **opening the specific object once and using the opened handle**, avoiding "check path → reuse path" sequences that invite races.

## 14. TOCTOU: Errors Between Check and Use

TOCTOU (*Time Of Check To Time Of Use*) occurs when state is checked at one moment, yet the file changes before the subsequent operation.

Unsafe example:

```java
Path candidate = root.resolve(userSuppliedName).normalize();

if (candidate.startsWith(root)
        && !Files.isSymbolicLink(candidate)
        && Files.isReadable(candidate)) {
    // Another process can swap candidate after these checks.
    return Files.readAllBytes(candidate);
}
```

This snippet intentionally illustrates the risk; `root` and `userSuppliedName` must be declared, with input validation and exception handling. Beyond the final-symlink race, `candidate.startsWith(root)` checks only a **syntactically normalized path**, which does not guarantee the real path stays inside `root` if a parent directory contains a symlink.

Mitigations depending on risk level:

1. **Never let clients pass arbitrary paths**; map resource IDs to server-managed storage keys.
2. Configure storage directories with proper OS permissions so untrusted actors cannot swap entries or symlinks.
3. Pass `NOFOLLOW_LINKS` open options when forbidding final symlinks; also evaluate every path component.
4. On supporting providers, consider `SecureDirectoryStream` to perform relative operations through a directory handle and reduce directory-entry resolution races.
5. For newly created files, use `StandardOpenOption.CREATE_NEW` to avoid overwriting existing entries where appropriate; combine with directory permissions and related options.
6. Design `IOException` handling around the real operation; never treat a pre-check as a guaranteed pass.
7. For high-security requirements, verify file identity and permissions on the OS/resource handle as supported by the environment, rather than relying on string paths.

`Path.toRealPath()` resolves the real path per contract, yet even that result **can become stale immediately after the call**. Never turn normalization into a guarantee against symlink swaps.

## 15. `toRealPath()` and Canonical Paths: Use with Accurate Semantics

Comparison:

| API | Primary Effect |
| --- | --- |
| `path.toAbsolutePath()` | Produces an absolute form using filesystem context |
| `path.normalize()` | Simplifies `.` and `..` syntax; does not touch the real filesystem |
| `path.toRealPath()` | Returns the real path of an existing entry, following links by default via provider |
| `path.toRealPath(NOFOLLOW_LINKS)` | Returns the real path while optionally not following symbolic links per contract |
| `Files.readSymbolicLink(path)` | Returns the target stored inside a symlink, possibly relative or non-existent |

`toRealPath()` can throw `NoSuchFileException`, `FileSystemLoopException`, or `IOException` if unresolvable. `normalize()` does not verify file existence. Platform specifics also affect case sensitivity and aliasing.

Never print `toRealPath()` (or internal root paths) in HTTP error responses solely for diagnostics; those paths can reveal usernames, mounts, or deployment layouts. Return stable public error codes and store diagnostics under proper access policies.

## 16. Directory Tree Traversal and Symbolic Link Loops

`Files.walkFileTree(start, visitor)` by default **does not follow symlinks**. Passing `FileVisitOption.FOLLOW_LINKS` lets traversal enter linked directories and potentially hit cycles.

```java
Files.walkFileTree(
        root,
        java.util.EnumSet.of(
                java.nio.file.FileVisitOption.FOLLOW_LINKS),
        Integer.MAX_VALUE,
        visitor);
```

This snippet requires `root`, a `FileVisitor<Path> visitor`, and imports; it is not standalone. With `FOLLOW_LINKS`, Java detects cycles; `FileSystemLoopException` may be passed to `visitFileFailed`. The visitor author must decide how to handle it.

When **there is no need to follow links**, keep the default no-follow behavior and inspect symlink entries explicitly if needed. Especially when deleting or archiving directory trees, following links outside the root can touch out-of-scope data. Never run a "directory cleanup" on untrusted paths with `FOLLOW_LINKS` without knowing the exact impact.

### Do not assume directory listings are snapshots

`Files.walk` or `walkFileTree` can observe state changing mid-traversal. Deleted entries, changed permissions, or swapped links can make an iteration fail partway. Diagnostics must handle per-entry exceptions and never treat the returned listing as an atomic snapshot.

## 17. Windows, Linux, macOS, and Provider Specifics

| Topic | What Can Vary |
| --- | --- |
| Symlink creation | Filesystem, OS privileges, policy, developer mode/elevated privileges on Windows |
| POSIX permission bits | Common on Unix-like filesystems; do not assume present on Windows/NTFS |
| ACLs | Available on Windows/NTFS and some other filesystems; not equivalent to POSIX bits |
| DOS attributes | Tied to FAT/NTFS or related providers; absent on many stores |
| Case sensitivity | NTFS, APFS, ext4, etc. can be configured/interpreted differently |
| Separator/path syntax | Windows/Unix and filesystem providers differ in representation |
| Symlink/junction/reparse point | OS-specific link types are not necessarily reported identically via one API |
| Deleting open files | Sharing/locking semantics differ sharply between Windows and POSIX |
| Atomic rename | Depends on file store/provider and `ATOMIC_MOVE` support |
| Timestamp precision | Timestamps may be rounded or updated under different rules |
| Network filesystems | Caching, credentials, network failures, eventual visibility, remote permissions |
| Virtual filesystems | ZIP filesystems, in-memory providers, and read-only stores expose different operation sets |

Never branch all behavior on hardcoded `System.getProperty("os.name")`. Probe **specific capabilities** on the path/file store and **test the real operation** when authorized. A single OS can mount stores with differing capabilities, or the same store can enforce stricter policies between CI and production.

## 18. Writing Portable Tests Instead of Single-Machine Tests

A well-designed test:

- Creates files/directories **only inside a test-owned temp directory**.
- Uses explicit **skip/assumption** branches for optional features like symlinks/POSIX views when unsupported or unpermitted.
- Distinguishes **unsupported** from **supported yet unexpectedly failing**; never blanket-catch every exception and report PASS.
- Never expects identical POSIX permission strings or ACLs on all platforms.
- Never alters permissions/ownership on existing user files or shared CI directories.
- After creating a link, verifies via specific APIs such as `readAttributes(..., NOFOLLOW_LINKS)`.
- Tests broken links, relative links, target permissions, and cleanup.
- Does not rely on identical listing order or timestamp precision across filesystems.
- For security-critical code, adds tests with an actor swapping symlinks concurrently or in controlled environments, noting race non-determinism.

### Complete Java 17+ example: conditional symlink test when supported

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

Output when symlinks are supported and all checks pass:

```text
PASS: symlink invariants
```

If the provider/policy forbids creating links:

```text
SKIP: symlink cannot be created
```

**Difference from an "always PASS" test:** if link creation succeeds yet `readAttributes`, `isSameFile`, or `readString` fails unexpectedly, the error is not swallowed by the link-creation catch block. If data mismatches, `AssertionError` fails the test. Skipping is strictly scoped to the optional link-creation step.

In larger test suites, classify skip reasons (unsupported/permission/other I/O) to aid operations diagnostics; this minimal example prints one generic message with no JUnit dependency.

## 19. Diagnosing Permission Errors Without Exposing Internal Paths

When an I/O action is denied, operators may need log entries like:

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

`AccessDeniedException.getFile()`, `FileSystemException.getReason()`, or `exception.getMessage()` can expose paths and provider details. When full diagnostics are needed, route them to protected channels with controlled retention and access policies; **public responses** only need stable error codes.

Tests for public-message safety should intentionally construct paths containing sensitive sentinel names and assert that responses/serializers never echo them. Distinguish process-level file permission errors from **user business authorization**; both layers can map to 403/404/500 depending on API policy.

## 20. Pitfalls to Avoid

1. **"`Files.exists` returning `false` guarantees the file doesn't exist."** False: it may be indeterminable due to access errors.
2. **"A broken link means no directory entry exists."** False: `NOFOLLOW_LINKS` can prove the link entry still exists.
3. **"`Files.isSymbolicLink` returning `false` proves it's not a symlink."** Not necessarily if the type couldn't be determined due to an I/O error.
4. **"`NOFOLLOW_LINKS` blocks symlinks in every parent directory."** Insufficient: understand API contracts and directory/path security design.
5. **"`readSymbolicLink` returns an absolute path."** It may return a relative target stored in the link.
6. **"Deleting a symbolic link deletes the target too."** False for `Files.delete(link)` under normal behavior.
7. **"A hard link is just another name for a symlink."** False; identity and content semantics differ.
8. **"`isReadable == true` means reading will surely succeed."** False: TOCTOU and other failures can still break I/O.
9. **"`isWritable == false` always means an ACL denied it."** False: it could be indeterminable or governed by another policy.
10. **"Every OS supports POSIX permissions."** False; inspect the file store's supported views.
11. **"Windows can never create symlinks."** False; depends on OS version, privileges, and provider.
12. **"Every file store on Linux is identical."** False; network/ZIP/FUSE/container stores can differ.
13. **"`normalize` and `toRealPath` suffice against path traversal."** False if symlink races or authorization gaps remain.
14. **"Having an ACL view means the web user is authorized."** False; OS permissions differ from application policy.
15. **"`Files.walkFileTree` follows links by default."** False; you must explicitly pass `FOLLOW_LINKS`.
16. **"Symlink cycles are always handled silently."** False; following links can raise `FileSystemLoopException`.
17. **"Timestamps and traversal order are identical across Windows/macOS/Linux."** False; write contract-based tests.
18. **"A test failing to create a symlink means symlink-handling code is broken."** Not necessarily; the feature may be unsupported or blocked by policy.
19. **"Catch every `IOException` and report SKIP."** False: that hides real bugs once the feature is confirmed supported.
20. **"Printing raw paths for debugging is harmless."** It can expose usernames, server layouts, and private storage keys.

## 21. Applied Exercises

### Exercise A — Broken link

Create symlink `broken.txt -> missing.txt` in a temporary directory. Predict `exists` with/without `NOFOLLOW_LINKS`, `isSymbolicLink`, and `readSymbolicLink`. Why do the results differ?

### Exercise B — POSIX/ACL capability

On your machine, use `Files.getFileStore(path)`, `supportsFileAttributeView(PosixFileAttributeView.class)`, and `AclFileAttributeView.class`. Compare two different file stores if available. Why shouldn't one result become a blanket OS rule?

### Exercise C — Race between check and use

One process calls `Files.isRegularFile(candidate, NOFOLLOW_LINKS)`, and another process swaps the entry for a symbolic link before `Files.readString(candidate)`. Explain the TOCTOU risk and propose mitigations using directory restrictions, open options, and handles.

### Exercise D — Directory traversal

A ZIP archive contains entry `../../outside.txt`. Why is `root.resolve(name).normalize().startsWith(root)` still insufficient if a subdirectory inside `root` can be swapped for a symlink? When operating on a directory tree concurrently modified by other users, which provider capability should be considered?

### Exercise E — Portable tests on CI

Modify `SymlinkInvariantTest` to log the skip reason to an internal channel without printing raw paths in public output. In an environment lacking symlink support, why skip symlink-specific tests instead of failing the entire build (when the feature is optional)?

### Exercise F — Open files and cleanup

Try opening a `FileChannel`, then deleting/renaming the file in the same process on different OSes. Record actual behavior, without writing portable tests assuming Windows and POSIX behave identically. Close the channel and safely delete temporary data afterward.

## 22. Self-Check Questions

1. How does `Files.isSymbolicLink(path)` differ from `Files.isRegularFile(path, NOFOLLOW_LINKS)`?
2. When a symlink's target is deleted, why can `Files.exists(link)` and `Files.exists(link, NOFOLLOW_LINKS)` differ?
3. What is the `Path` returned by `Files.readSymbolicLink(link)` relative to?
4. What is the meaning and limitation of `NOFOLLOW_LINKS` in preventing symlink attacks?
5. When should you use `Files.readAttributes(..., NOFOLLOW_LINKS)` instead of `Files.isSymbolicLink` alone?
6. Does `Files.isReadable(path)` returning `true` replace catching `IOException`?
7. What does `FileStore.supportsFileAttributeView` tell you, and what does it not guarantee?
8. Can POSIX permissions and Windows ACLs be unified completely?
9. Why can checking permissions and then opening a file create a TOCTOU flaw?
10. Does `Files.delete(link)` automatically delete the symlink target's content?
11. Why is `Path.normalize()` not a reliable security root check?
12. When using `FOLLOW_LINKS` in `walkFileTree`, what error type must you account for?
13. If CI cannot create symlinks, how do you organize tests so real bugs in other functionality are still caught?
14. Why test across multiple file store types rather than just multiple OS names?
15. Should you include absolute paths or owner names on HTTP error pages when `AccessDeniedException` occurs?

## 23. Java 17 References

- [`Files` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): create/read symbolic links, exists, readAttributes, access probes, walkFileTree.
- [`Path` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): normalize, toAbsolutePath, toRealPath, and provider semantics.
- [`LinkOption` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS`.
- [`FileStore` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html): `supportsFileAttributeView`.
- [`java.nio.file.attribute` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/package-summary.html): Basic/POSIX/DOS/ACL/User-defined attribute views.
- [`SecureDirectoryStream` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): directory-entry operations reducing races where supported by the provider.
- [`FileVisitOption` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileVisitOption.html): `FOLLOW_LINKS` during tree traversal.

## 24. Key Takeaways

**A symbolic link is a separate entry pointing to a target**, and `NOFOLLOW_LINKS` applies only to APIs that honor it. For broken links, a default existence check can return `false` while checking the link itself with `NOFOLLOW_LINKS` returns `true`.

**Permissions and file attributes depend on the provider/file store, OS, process identity, and timing**. `Files.isReadable`/`isWritable` never replace actually opening the file; POSIX/DOS/ACL views must be detected dynamically. For security-sensitive code, prevent TOCTOU by managing roots/handles, proper directory permissions, no-follow open options, and component checks — never `normalize()` alone.

High-quality tests **use only temporary resources**, detect optional capabilities, distinguish `SKIP` from `FAIL`, avoid assuming identical permission/symlink output across all platforms, and never leak internal paths in public messages.
