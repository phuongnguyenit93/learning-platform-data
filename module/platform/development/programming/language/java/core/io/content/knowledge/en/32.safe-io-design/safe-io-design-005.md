# `SecureDirectoryStream` and Provider Support in Java NIO.2

## 1. Why Is `SecureDirectoryStream` Needed?

A Java application may process files inside a directory that users or other processes can modify. The familiar “check path then act” workflow has an exploitable time gap:

~~~java
Path file = root.resolve(userName);
if (Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
    Files.delete(file);
}
~~~

**This is a snippet illustrating risk, not a safe deletion pattern.** Between the `isRegularFile` check and `delete`, another actor can replace a path component. At that point, the two calls can refer to **two different file objects**. This class of bug is called *time-of-check to time-of-use*, abbreviated **TOCTOU**.

`SecureDirectoryStream<T>` in `java.nio.file` solves an important part of this problem: it provides operations on **paths relative to an already-open directory** instead of repeatedly re-resolving from an absolute path name that can be swapped. This interface is designed for applications that need to traverse directory trees or operate on files in a way that resists *race conditions* when supported by the provider/OS.

~~~text
Without a directory-anchoring handle:
check /safe/inbox/item.txt
       |
  attacker swaps inbox -> symlink to /other
       |
delete /safe/inbox/item.txt  => may hit a different object

With SecureDirectoryStream:
open /safe/inbox  --> handle H to the open directory
       |
       +-- deleteFile(Path.of("item.txt"))
                operates relative to H
                even if the name "inbox" is swapped
~~~

This is a **threat model** diagram; it does not mean every operation on every system produces the same outcome. `SecureDirectoryStream` requires provider and OS support, and it does not replace permission controls, authentication, hard-link protection, or sandbox policies.

**Main idea:** `SecureDirectoryStream` strengthens defense against path-swapping/symbolic-link replacement attacks in operations relative to an open directory. It is **not automatically present on every filesystem and provider**; security-sensitive applications must check support at runtime.

## 2. Relationship Between `DirectoryStream` and `SecureDirectoryStream`

`DirectoryStream<T>` supports iterating over the entries of a directory, typically obtained via:

~~~java
try (DirectoryStream<Path> entries = Files.newDirectoryStream(root)) {
    for (Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

This is an illustrative snippet with an existing `Path root`, requiring `IOException` handling. With a regular `DirectoryStream<Path>`, the iterator only yields `Path` objects for the application to pass to `Files.*` by name. Receiving a path name from the iterator **does not lock** the entry or guarantee the entry remains the same object when acted upon.

`SecureDirectoryStream<T>` **extends `DirectoryStream<T>`** and adds open-directory-context operations:

| Method | Purpose |
| --- | --- |
| `newDirectoryStream(T path, LinkOption... options)` | Opens a subdirectory relative to the open directory, returning another `SecureDirectoryStream<T>`. |
| `newByteChannel(T path, Set<? extends OpenOption> options, FileAttribute<?>... attrs)` | Opens/creates a file via a relative path and returns a `SeekableByteChannel`. |
| `deleteFile(T path)` | Deletes a file entry (also used to delete a symbolic link) relative to the current directory. |
| `deleteDirectory(T path)` | Deletes a directory entry relatively, subject to the corresponding directory-deletion rules. |
| `move(T src, SecureDirectoryStream<T> targetDir, T target)` | Moves an entry from the open directory to another open target directory. |
| `getFileAttributeView(Class<V> type)` | Opens an attribute view of the open directory itself. |
| `getFileAttributeView(T path, Class<V> type, LinkOption... options)` | Opens an attribute view of a relative entry. |
| `close()` | Releases the open directory stream/handle. |

The type parameter `T` in Java NIO is normally `Path`. When opened from `Files.newDirectoryStream(root)`, the declared type is typically `DirectoryStream<Path>`; **do not cast immediately** without checking the instance.

## 3. Provider Support Is an Optional Feature

The `SecureDirectoryStream` API has existed since Java 7, and Java 17 includes all of the methods above. However, **the existence of the interface does not guarantee that a provider implements it**.

Java 17 Javadoc specifies: if the implementation supports this feature, the `DirectoryStream` returned by `newDirectoryStream` may be a `SecureDirectoryStream`. The application must inspect the actual runtime object:

~~~java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    if (stream instanceof SecureDirectoryStream<?>) {
        System.out.println("Provider hỗ trợ tại vị trí này");
    } else {
        System.out.println("Không có SecureDirectoryStream");
    }
}
~~~

This is an illustrative snippet requiring `java.nio.file.*` imports, a `root` variable, and `IOException` handling.

Actual support depends on:

- The **FileSystemProvider** selected by the `Path`'s filesystem.
- Whether the operating system provides a handle-relative open/operation mechanism.
- The JDK version, provider, filesystem type, and execution environment (network-mounted filesystems, virtual filesystems, containers, etc.).

**Do not hardcode rules like “Linux always has it”, “Windows never has it”, or “ZIP filesystem definitely has it”.** Actual support must be checked at runtime; providers vary.

### 3.1. Why Can't You Call These Methods Directly on `DirectoryStream`?

~~~java
DirectoryStream<Path> stream = Files.newDirectoryStream(root);

// Type-invalid: DirectoryStream does not define deleteFile.
// stream.deleteFile(Path.of("data.txt"));
~~~

You must check and use the object as `SecureDirectoryStream<Path>`:

~~~java
if (stream instanceof SecureDirectoryStream<?>) {
    @SuppressWarnings("unchecked")
    SecureDirectoryStream<Path> secure =
            (SecureDirectoryStream<Path>) stream;
    secure.deleteFile(Path.of("data.txt"));
}
~~~

These are **illustrative snippets**, without complete resource open/close handling. The cast is appropriate in the example because `stream` is declared as `DirectoryStream<Path>`; do not extrapolate that cast to custom `DirectoryStream<T>` types with different type parameters.

### 3.2. What Should You Do If the Provider Does Not Support It?

It depends on requirements:

1. **The task requires path-race protection as a security condition:** *fail closed*, abort the operation, and report that the provider/environment does not meet the requirement.
2. **The directory is under exclusive application control, and no one else can alter entries during processing:** you may consider standard `Files.*` APIs under a proven trust model.
3. **Cross-platform support is needed while preserving equivalent safety:** change the architecture (dedicated staging area with strict permissions, immutable file versions, a dedicated privileged service, or a verified OS-equivalent mechanism).

**Do not build a “fallback” by merely calling `toRealPath()`, `normalize()`, `Files.isSymbolicLink()`, and then `Files.delete()` and claiming equivalence:** check-then-use still has a race window whenever another actor can modify the path.

## 4. Relative Paths and Anchoring to a Directory Handle

Most importantly, the secure methods generally accept **paths relative to the open directory**:

~~~java
Path name = Path.of("invoice.txt");
SeekableByteChannel channel =
        secure.newByteChannel(name, Set.of(StandardOpenOption.READ));
~~~

This snippet assumes `secure` is a valid, already-open `SecureDirectoryStream<Path>`.

When `name` is a relative path, the operation uses the current directory handle; renaming the directory in the path namespace does not automatically redirect the handle to another directory.

**Absolute paths are an exception to avoid.** According to the Javadoc, if an absolute path is passed to these methods, resolution may follow absolute-path semantics and defeat the goal of anchoring to the open directory. Reject absolute paths for operations intended to remain inside a root.

### 4.1. Do Not Accept Path Traversal

Even when using a secure stream, you must still reject paths outside the allowed name domain:

~~~text
Valid for an API allowing only a single filename:
  report.txt
  data_001.bin

Must be rejected under the single-component rule:
  ../secret.txt
  subdir/../../secret.txt
  /etc/passwd
  ./
  ..
~~~

Checking `normalize()` and `startsWith(root)` on absolute paths **does not fully protect** against symlink races or external directory mutations. A more auditable approach is restricting user input to a **single entry name**, rejecting `.`/`..`, path separators, absolute paths, special names, and invalid names per filesystem/application rules.

An illustrative validator example:

~~~java
static Path safeSingleName(FileSystem fs, String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Tên rỗng");
    }
    Path name = fs.getPath(raw);
    if (name.isAbsolute()
            || name.getNameCount() != 1
            || name.toString().equals(".")
            || name.toString().equals("..")) {
        throw new IllegalArgumentException("Không phải tên entry đơn");
    }
    return name;
}
~~~

This is a **code snippet**; it requires `java.nio.file.FileSystem` and `Path`. For inputs from the Internet, you must also define name policies, Unicode normalization, forbidden characters, reserved names, and system-appropriate case-folding. A validator does not replace authorization/ownership checks; it only narrows the name scope a user may specify.

### 4.2. Multiple Directory Levels: Traverse Level by Level Under Control

If the application genuinely allows operations inside subdirectories, open subdirectories via directory handles and control symbolic links at **every step**:

~~~java
try (SecureDirectoryStream<Path> sub =
        secure.newDirectoryStream(
                Path.of("uploads"), LinkOption.NOFOLLOW_LINKS)) {

    try (SeekableByteChannel file = sub.newByteChannel(
            Path.of("report.txt"),
            Set.of(StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS))) {
        // Read data from the opened channel.
    }
}
~~~

This is an illustrative snippet (requiring a valid `secure` variable, imports, and exception handling). `NOFOLLOW_LINKS` on `newDirectoryStream` prevents opening the subdirectory if that final entry itself is a symbolic link. Likewise, `NOFOLLOW_LINKS` in `newByteChannel`'s open options requires the operation to fail if the target entry is a symbolic link.

**Do not mix arbitrary parent traversal into a user-supplied path string** and assume it is safe just because `SecureDirectoryStream` is used. Allowed paths should be constrained and traversed component by component through trusted handles.

## 5. Symbolic Links and `NOFOLLOW_LINKS`

A common cause of path races is **symbolic links**: an attacker replaces a directory entry with a link pointing outside the allowed scope.

`LinkOption.NOFOLLOW_LINKS` specifies that the target must not follow symlinks in the corresponding operation:

| Operation | Example Using No-Follow | Meaning |
| --- | --- | --- |
| Open subdirectory | `secure.newDirectoryStream(child, LinkOption.NOFOLLOW_LINKS)` | Fails if that entry is a symlink. |
| Open file byte channel | `secure.newByteChannel(file, Set.of(READ, LinkOption.NOFOLLOW_LINKS))` | Fails if the target file entry is a symlink. |
| Read entry metadata | `secure.getFileAttributeView(file, BasicFileAttributeView.class, LinkOption.NOFOLLOW_LINKS)` | Inspects attributes of the entry/link itself instead of following the symlink. |

Note that **not every method accepts `LinkOption`**: `deleteFile`, `deleteDirectory`, and `move` have their own contracts. Do not try passing `NOFOLLOW_LINKS` to `deleteFile`, as no such overload exists.

`NOFOLLOW_LINKS` does not replace restricting absolute paths or paths containing `..`. Nor does it prevent every change caused by hard links, mounts, filesystem permissions, or another process that already opened the file earlier.

## 6. A Complete, Standalone, Safe Java 17+ Example

This example:

1. Creates a **dedicated temporary directory** and a file `message.txt` containing `HELLO`.
2. Calls `Files.newDirectoryStream(root)`.
3. If the provider supports `SecureDirectoryStream`, opens the file **by relative name** with `NOFOLLOW_LINKS`, reads the content with `SeekableByteChannel`, and uses `deleteFile` to delete the entry.
4. If unsupported, **does not pretend to substitute a less safe API**; the program prints that the secure operation was refused.
5. Closes the stream and channel with `try-with-resources`, then cleans up the temporary file/directory.

Save as `SecureDirectoryStreamDemo.java`:

~~~java
import java.io.IOException;
import java.nio.channels.Channels;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SecureDirectoryStream;
import java.nio.file.StandardOpenOption;
import java.util.Set;

public class SecureDirectoryStreamDemo {

    public static void main(String[] args) throws IOException {
        Path root = Files.createTempDirectory("sds-demo-");
        Path file = root.resolve("message.txt");

        try {
            Files.writeString(
                    file, "HELLO", StandardCharsets.US_ASCII,
                    StandardOpenOption.CREATE_NEW);

            try (DirectoryStream<Path> stream =
                    Files.newDirectoryStream(root)) {

                if (stream instanceof SecureDirectoryStream<?>) {
                    @SuppressWarnings("unchecked")
                    SecureDirectoryStream<Path> secure =
                            (SecureDirectoryStream<Path>) stream;

                    Path name = Path.of("message.txt");

                    try (SeekableByteChannel channel =
                            secure.newByteChannel(
                                    name,
                                    Set.of(
                                            StandardOpenOption.READ,
                                            LinkOption.NOFOLLOW_LINKS))) {

                        byte[] bytes = Channels.newInputStream(channel)
                                .readAllBytes();
                        System.out.println("mode=SECURE");
                        System.out.println("text=" +
                                new String(bytes, StandardCharsets.US_ASCII));
                    }

                    secure.deleteFile(name);
                    System.out.println("deleted=" +
                            !Files.exists(file, LinkOption.NOFOLLOW_LINKS));
                } else {
                    System.out.println("mode=UNAVAILABLE");
                    System.out.println("action=REFUSED");
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(root);
        }
    }
}
~~~

Compile/run:

~~~bash
javac SecureDirectoryStreamDemo.java
java SecureDirectoryStreamDemo
~~~

If the filesystem/provider supports `SecureDirectoryStream` and the temp file works normally, stdout is:

~~~text
mode=SECURE
text=HELLO
deleted=true
~~~

If the provider **does not** support it, stdout is:

~~~text
mode=UNAVAILABLE
action=REFUSED
~~~

The two outputs above are **two environment-dependent branches**, not a single fixed outcome across all OSes/JDKs. If filesystem operations lack permissions or encounter an I/O error, the program may throw `IOException` instead of completing a branch; that is the right behavior when a security operation fails.

### 6.1. Why Check the Instance Instead of Just Checking the OS?

`Files.newDirectoryStream(root)` has declared return type `DirectoryStream<Path>`. If the actual runtime object implements `SecureDirectoryStream`, we can use the extended API. Support depends on the OS and provider, so checking the actual runtime type is **more accurate** than relying on an OS name or filesystem type written in config.

### 6.2. Why Read via `SeekableByteChannel`?

`secure.newByteChannel(...)` binds the file-open operation to the directory handle instead of forcing the program to call `Files.newInputStream(root.resolve(name))` again (which could re-resolve the path). `Channels.newInputStream(channel)` merely wraps the **already-open channel**, so it does not change the file object bound to that handle.

`newByteChannel` returns a channel independent of the lifetime of the directory stream that opened it; however, the example keeps the stream open until `deleteFile` finishes so the directory handle remains available for deletion.

### 6.3. Why Clean Up with `Files.deleteIfExists` at the End?

The `finally` block cleans up a **temporary directory created and owned by the program itself**, after the secure operations have finished. It is test cleanup logic, **not an equivalent security fallback** if handling an attacker-controlled directory. If the temporary root were controlled by an untrusted actor, the example's safety assumptions would need re-evaluation.

## 7. Opening Files with `newByteChannel`

Java 17 signature:

~~~java
SeekableByteChannel newByteChannel(
        T path,
        Set<? extends OpenOption> options,
        FileAttribute<?>... attrs
) throws IOException;
~~~

This is a **method signature**, not code to paste verbatim inside `main`.

Common options:

- `StandardOpenOption.READ`: read.
- `StandardOpenOption.WRITE`: write.
- `StandardOpenOption.CREATE_NEW`: create only when the file does not exist; useful to avoid overwriting an existing entry.
- `StandardOpenOption.CREATE`: create if absent, without rejecting an existing entry; use caution with untrusted files.
- `StandardOpenOption.TRUNCATE_EXISTING`: truncate an existing file when opening for write; dangerous if the target is not properly validated.
- `LinkOption.NOFOLLOW_LINKS`: fail if the final path entry is a symbolic link.

To create a new file relative to the directory handle:

~~~java
try (SeekableByteChannel created = secure.newByteChannel(
        Path.of("new-item.dat"),
        Set.of(
                StandardOpenOption.WRITE,
                StandardOpenOption.CREATE_NEW,
                LinkOption.NOFOLLOW_LINKS))) {

    ByteBuffer data = StandardCharsets.UTF_8.encode("safe payload");
    while (data.hasRemaining()) {
        created.write(data);
    }
}
~~~

This is an illustrative snippet requiring `ByteBuffer`, `StandardCharsets`, and related imports. `CREATE_NEW` avoids overwriting an existing entry; however, it does not mean the user input was authorized by business rules to create that name. Still validate names/permissions and enforce byte limits.

The `FileAttribute<?>... attrs` parameter can set attributes at file creation time **when supported by the provider**; unsupported attributes may throw `UnsupportedOperationException`. Do not assume every provider accepts POSIX attributes.

## 8. Deleting Files, Symlinks, and Directories

`secure.deleteFile(relativeName)` deletes a file **entry** relative to the directory stream; if the entry is a symbolic link, the behavior applies to the link entry itself, not deleting the link's target. `secure.deleteDirectory(relativeName)` deletes a directory entry per filesystem contract, not “recursive tree deletion”.

~~~java
secure.deleteFile(Path.of("obsolete.tmp"));
secure.deleteDirectory(Path.of("empty-folder"));
~~~

This is an illustrative snippet: both names must be valid under the directory handle and the provider must have delete permission; the directory must satisfy the filesystem's directory-deletion rules (typically must be empty). Errors such as `NoSuchFileException`, `DirectoryNotEmptyException`, `AccessDeniedException`, or `IOException` must be handled per business logic.

**Risks outside the scope of a secure stream:** if an attacker has permission to modify the contents inside an already-open file or create hard links to it, directory-relative APIs alone do not guarantee content trustworthiness. `SecureDirectoryStream` primarily addresses **locating files in a directory tree when names can be swapped**; it does not replace the permission system.

### 8.1. Recursive Directory Tree Deletion Can Be More Complex

To delete an entire tree that an attacker can mutate concurrently, you should not simply list `Files.walk(root)` and call `Files.delete(path)` on absolute paths. You need a strategy that operates relatively using directory handles at each level, avoids following symlinks, checks permissions, and bounds depth/entry counts. In environments without `SecureDirectoryStream` support, **do not claim** an equivalent recursive deletion has the same TOCTOU resistance.

## 9. `move()`: Operating Between Two Open Directories

API:

~~~java
void move(
        T srcpath,
        SecureDirectoryStream<T> targetdir,
        T targetpath
) throws IOException;
~~~

Example:

~~~java
try (SecureDirectoryStream<Path> destination =
        secure.newDirectoryStream(
                Path.of("archive"), LinkOption.NOFOLLOW_LINKS)) {

    secure.move(
            Path.of("input.txt"),
            destination,
            Path.of("input-archived.txt"));
}
~~~

This is an illustrative snippet with `secure` pointing to the source directory containing a valid `archive` subdirectory.

Per the Java 17 Javadoc, `move` behaves similarly to `Files.move` with `ATOMIC_MOVE`: the move is performed as an atomic filesystem operation. However:

- The provider may throw `AtomicMoveNotSupportedException` when an atomic move cannot be performed.
- If the target already exists, whether it replaces or fails is **implementation-specific**.
- There is no `REPLACE_EXISTING` parameter on this `SecureDirectoryStream.move` method; do not assume an overwrite policy.
- `srcpath` and `targetpath` should be constrained as **relative paths** within trusted directories. Using absolute paths may bypass the intended directory-handle semantics.
- Atomic rename does not replace data validation, permission checks, durability of changes, or a crash-recoverable version publishing workflow.

## 10. Safely Retrieving Metadata via a Directory Handle

`getFileAttributeView` retrieves/modifies file metadata without reconstructing an absolute path by name:

~~~java
BasicFileAttributeView view = secure.getFileAttributeView(
        Path.of("report.txt"),
        BasicFileAttributeView.class,
        LinkOption.NOFOLLOW_LINKS);

if (view != null) {
    BasicFileAttributes attrs = view.readAttributes();
    System.out.println("size=" + attrs.size());
}
~~~

This is an illustrative snippet requiring `java.nio.file.attribute.BasicFileAttributeView` and `BasicFileAttributes`. Depending on the provider, an attribute view may be unsupported and return `null`. Besides `BasicFileAttributeView`, some providers may support specialized attribute views, though parity across filesystems should not be assumed.

`NOFOLLOW_LINKS` targets the metadata of the final entry rather than the link target. Although a secure directory handle reduces the risk of *locating the entry*, metadata is still a **point-in-time snapshot**: another writer can modify the file's contents or metadata after reading. For payload/ACL/version consistency, use additional strategies such as immutable files, exclusive ownership, or synchronization protocols.

### 10.1. Attribute View of the Directory Itself

~~~java
BasicFileAttributeView dirView =
        secure.getFileAttributeView(BasicFileAttributeView.class);
BasicFileAttributes dirAttrs = dirView.readAttributes();
~~~

This is an illustrative snippet; if the provider does not support the requested view it may return `null`, so production code must check before dereferencing.

The benefit of obtaining a view from the open directory is avoiding re-resolving a mutable path name. Still, it does not make attribute reads atomic transactions with other operations in the program.

## 11. `SecureDirectoryStream` Is Not a Complete Sandbox

What the interface aims to provide:

- Operating on paths relative to an **open directory** rather than a replaceable name string.
- Entering subdirectories using a new **secure directory handle**, optionally with `NOFOLLOW_LINKS`.
- Opening file byte channels, deleting, and moving entries with path-race-reducing semantics.
- Obtaining attribute views bound to the directory handle to reduce reliance on check-then-use over global path names.

What it **does not guarantee on its own**:

1. **Does not provide per-user authorization:** the application must still verify which user may read/delete which file.
2. **Does not block all hard links:** a non-symlink entry can still point to an inode the application should not touch; filesystem permissions and policies remain necessary.
3. **Does not lock file contents from other writers:** opening the right file channel does not mean bytes cannot be modified concurrently.
4. **Does not unconditionally prevent mount/namespace changes:** the security model depends on the OS and attacker privileges; evaluate your specific threat model.
5. **Does not eliminate all TOCTOU outside filesystem operations:** metadata verification, format parsing, checksum checks, and business decisions are separate steps.
6. **Does not automatically protect symlinks inside a given path if structure is unchecked:** you must step level by level and pass `NOFOLLOW_LINKS` where needed.
7. **Does not guarantee every provider supports it:** you must check the runtime object and handle the unsupported branch.
8. **Does not replace TLS, digital signatures, or data validation:** a “properly located” path does not mean the data is trustworthy.

A safe system must clearly define OS permissions, who can modify directories and entries, which data comes from users, which provider actually runs, and the consequences when an operation fails.

## 12. Sample Race Conditions and How to Redesign

### 12.1. Mistake: `Files.isDirectory` Followed by Iterating Inside

~~~java
if (Files.isDirectory(root.resolve("incoming"))) {
    try (DirectoryStream<Path> entries =
            Files.newDirectoryStream(root.resolve("incoming"))) {
        // There is a race window between check and open.
    }
}
~~~

The `incoming` directory could be replaced with a symlink between the two calls; this is an **unsafe illustrative snippet in an untrusted environment**.

With a secure stream, if you already hold a trusted handle to `root`:

~~~java
try (SecureDirectoryStream<Path> incoming =
        rootSecure.newDirectoryStream(
                Path.of("incoming"), LinkOption.NOFOLLOW_LINKS)) {
    // Operate relative to the opened directory itself.
}
~~~

Note that **creating `rootSecure` initially** must also start from a trusted root source with proper protection. If an attacker can swap the root between selecting it and `Files.newDirectoryStream(root)` opening it, the resulting secure stream anchors to the directory **actually opened**, which may not be the one intended by business policy.

### 12.2. Mistake: Checking Symlink Status Then Doing a Normal Open

~~~java
if (!Files.isSymbolicLink(file)) {
    Files.newInputStream(file); // Another name may appear after the check.
}
~~~

**Risk-illustrating snippet.** When using `SecureDirectoryStream.newByteChannel(relativeName, Set.of(READ, NOFOLLOW_LINKS))`, follow-link control is specified directly in the directory-handle-relative file open, avoiding that check-then-open gap for the final entry.

### 12.3. Mistake: Ignoring the Unsupported Case

~~~java
DirectoryStream<Path> ds = Files.newDirectoryStream(root);
SecureDirectoryStream<Path> s =
        (SecureDirectoryStream<Path>) ds; // May throw ClassCastException.
~~~

A program that runs on machine A is not guaranteed to be safe or even work on machine B. Check `instanceof` and provide a clear fail-closed branch. Never “catch `ClassCastException` and fall back to `Files.delete`” if the original risk was a symlink/path race.

## 13. Lifecycle and Exception Handling Details

### 13.1. Closing the Directory Stream Promptly

Both `DirectoryStream` and `SecureDirectoryStream` implement `Closeable`, so:

~~~java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    // Check instanceof and perform operations here.
}
~~~

Closing the stream releases associated resources; secure-relative methods invoked on a closed stream may throw `ClosedDirectoryStreamException`. A child `SecureDirectoryStream` opened from a parent stream **has its own lifecycle** per contract: closing the parent does not automatically close the child. Similarly, channels opened from `newByteChannel` must be closed independently.

Thus the lifetimes of directory handles and file handles can be decoupled, though production code should make ownership explicit to prevent descriptor leaks.

### 13.2. Errors You May Need to Handle

| Error / Exception | Situation |
| --- | --- |
| `NoSuchFileException` | Entry no longer exists at access time. |
| `AccessDeniedException` | Permissions do not allow the operation. |
| `NotDirectoryException` | Name requested as a directory is not a directory (provider-dependent). |
| `DirectoryNotEmptyException` | Deleting a directory that still contains entries. |
| `ClosedDirectoryStreamException` | Calling a secure operation after the directory stream was closed. |
| `AtomicMoveNotSupportedException` | Unable to perform `move` atomically. |
| `UnsupportedOperationException` | Provider does not support the requested option/attribute. |
| `IOException` | Broader I/O errors (including races causing the target to vanish). |

Do not assume every operating system throws the exact same **specific exception subclass** in every situation; many specific subclasses are *optional specific exceptions*. When a security operation cannot complete as required, halt/roll back the business workflow appropriately instead of silently ignoring it.

### 13.3. Thread-Safety and Iteration

A directory stream is used to iterate entry names; the set of entries may change during iteration. Do not depend on iteration order, do not assume a snapshot, and do not use streams/channels from multiple threads in a way that creates data races. If asynchronous processing is needed, define which thread owns the directory handle and manage when it is closed.

## 14. A Safer Workflow for Handling File Uploads

Suppose a service receives a filename from a request and saves it into an upload directory:

1. **Authenticate and authorize** the user first; enforce upload count and size limits.
2. Select the root from trusted configuration; never take an absolute path from the user.
3. Open the root and **check `instanceof SecureDirectoryStream<?>`**; if unsupported by the provider when path-race protection is mandatory, reject the operation.
4. Constrain the filename to a **single relative component**; forbid absolute paths, `.`, `..`, and separator representations.
5. Use `newByteChannel(name, Set.of(WRITE, CREATE_NEW, NOFOLLOW_LINKS))` to create the entry, avoiding overwrites and symlink following.
6. Write data while counting bytes, checking quotas and size limits; handle partial writes as needed.
7. If the upload requires controlled commit, write to a trusted staging area, validate content, and use the designed publish workflow. Secure-relative `move` has atomic semantics but does not automatically add durability/authorization guarantees.
8. Close channels and directory streams according to lifecycle, delete temporary files on error, while still considering races/ownership during cleanup.
9. Log provider-unsupported, permission, size/quota, and rejection errors without exposing sensitive paths to the client.

Do not treat `CREATE_NEW` as a guarantee that “because we created this file, it is definitely safe”: the data may come from an untrusted source, names may collide at the business level, and many other security requirements still apply.

## 15. When Is Regular `Files.*` Still Appropriate?

`Files.readString`, `Files.copy`, `Files.delete`, `Files.move`, and `Files.walkFileTree` have very convenient APIs. They do not automatically become wrong simply because `SecureDirectoryStream` exists.

Choose `Files.*` when:

- Files/directories are application-owned with **protective OS permissions**, and no untrusted actor can swap paths between operations.
- Reading immutable configuration files, internal build data, test fixtures, or batch jobs without a significant path-race threat model.
- The provider does not support secure streams, yet the workflow **is proven not to require** race protection between check and use.

Choose `SecureDirectoryStream` when:

- Deleting/moving/reading/writing in shared directories where untrusted actors may concurrently alter entries.
- Protecting against symlink swaps of adversary-controlled directory components.
- Traversing file trees or publishing entries via directory handles with a requirement to mitigate TOCTOU.
- You can **require the environment to support this API** or enforce a fail-closed policy.

If path-race protection is mandatory and the platform lacks an equivalent capability, the right solution may be **not deploying that feature on that platform**, rather than silently weakening guarantees.

## 16. Self-Check Exercises

1. **Is `SecureDirectoryStream` a class or an interface?** It is an interface extending `DirectoryStream<T>`.
2. **Does every `Files.newDirectoryStream(dir)` return a `SecureDirectoryStream`?** No; it depends on the provider and OS support.
3. **How do you check for support?** Check whether the runtime object is `instanceof SecureDirectoryStream<?>`; cast only when true.
4. **Why can `Files.isSymbolicLink(path)` followed by `Files.newInputStream(path)` be dangerous?** There is a TOCTOU gap between checking and using the name.
5. **What is the benefit of relative paths anchored to a directory handle?** It avoids re-resolving directory names globally when entries are renamed or swapped.
6. **What is the role of `NOFOLLOW_LINKS`?** It requests not following symbolic links in the corresponding operation, such as opening a subdirectory/file.
7. **Does `deleteFile` take a `NOFOLLOW_LINKS` parameter?** No; it has its own entry-deletion contract.
8. **Does `SecureDirectoryStream.move` guarantee overwriting the target?** No; when the target already exists, whether it replaces or fails is implementation-dependent.
9. **What can `move` throw if atomic move is unavailable?** `AtomicMoveNotSupportedException`.
10. **Does closing a parent secure directory stream automatically close child streams?** No. Child streams have their own lifetimes.
11. **Does closing a directory stream automatically close channels opened from it?** No. Channels have their own lifetimes.
12. **If the provider lacks support, can you claim a check-then-delete fallback provides the same guarantee?** No; if race protection is mandatory, fail closed or change the architecture.
13. **Is passing `../../etc/passwd` as a relative path safe just because a secure stream is used?** No; path-component validation and control are still required.
14. **Does `SecureDirectoryStream` prevent all hard-link attacks?** No; ownership, permissions, and the filesystem threat model must be considered.
15. **If a file is opened safely yet another writer can modify its contents, is the data automatically immutable?** No; version/ownership controls and consistent read/write coordination are still needed.
16. **If the program runs on Linux but a custom `FileSystemProvider` does not support SDS, can you use it?** Never assume; check at runtime and handle the unsupported case.
17. **Should you pass an absolute path to `secure.newByteChannel(...)` to stay inside the root?** No; an absolute path can bypass the open-directory anchoring semantics.
18. **If an application must prevent path races without controlling the initial root, is opening SDS enough to prove it is the right directory?** No; you must ensure the initial root handle points to a trusted directory.
19. **Does every `DirectoryStream` iteration reflect an immutable snapshot?** No; entries may change during iteration.
20. **Does `SecureDirectoryStream` replace upload content validation and quotas?** No; it focuses on relative path operations, not data validation.

## 17. Official Java 17 Documentation

- [SecureDirectoryStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): open-directory-relative semantics, supported methods, fallback notes, and exceptions.
- [DirectoryStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html): iteration and directory stream lifecycle.
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `newDirectoryStream`, `newByteChannel`, and standard file operations.
- [LinkOption — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` and operation-specific semantics.
- [FileSystemProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): provider's role in filesystem implementation.

**Remember:** `SecureDirectoryStream` operates against an **open directory handle**, helping prevent many races caused by entry/link swapping when operating on **relative paths**. Support depends on the provider and OS, so you must **check `instanceof` at runtime**. If race safety is mandatory and the provider lacks support, **fail closed** instead of substituting check-then-use and claiming equivalence. Always control path names, symlinks, permissions, lifetimes, and data integrity.