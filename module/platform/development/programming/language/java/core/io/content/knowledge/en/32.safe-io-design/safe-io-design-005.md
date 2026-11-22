# `SecureDirectoryStream` and Provider Support in Java NIO.2

## 1. Why Is `SecureDirectoryStream` Needed?

A Java application may process files in a directory that users or other processes can modify. The familiar "check path then act" workflow has a window that can be exploited:

~~~java
Path file = root.resolve(userName);
if (Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
    Files.delete(file);
}
~~~

**This snippet illustrates risk; it is not a safe deletion pattern.** After `isRegularFile` checks and before `delete`, another actor may replace a path component. The two calls may then refer to **two different file objects**. This bug class is called *time-of-check to time-of-use*, abbreviated **TOCTOU**.

`SecureDirectoryStream<T>` in `java.nio.file` addresses an important part of this problem: it provides operations on **paths relative to an open directory** instead of repeatedly resolving from an absolute path name that could be swapped. This interface is designed for applications that need to traverse directory trees or work with files in a *race-condition*-resistant manner when supported by the provider/OS.

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
                even if the name "inbox" is changed
~~~

This diagram illustrates a **threat model**; it does not mean every operation on every system yields the same outcome. `SecureDirectoryStream` requires support from the provider and operating system, and does not replace permission controls, authentication, hard-link protection, or sandboxing policies.

**Main point:** `SecureDirectoryStream` increases resistance against path-swap and symbolic-link-swap attacks on operations relative to an open directory. It is **not guaranteed to exist on every filesystem and provider**; security-sensitive applications must check support at runtime.

## 2. Relationship Between `DirectoryStream` and `SecureDirectoryStream`

`DirectoryStream<T>` supports iterating over a directory's entries, typically obtained via:

~~~java
try (DirectoryStream<Path> entries = Files.newDirectoryStream(root)) {
    for (Path entry : entries) {
        System.out.println(entry.getFileName());
    }
}
~~~

This is an illustrative snippet with an existing `Path root`, requiring `IOException` handling. With an ordinary `DirectoryStream<Path>`, the iterator only yields `Path` objects for the application to pass to `Files.*` calls. Having a path name from the iterator **does not lock** the entry or guarantee it remains the same object during later operations.

`SecureDirectoryStream<T>` **extends `DirectoryStream<T>`** and adds open-directory-context operations:

| Method | Purpose |
| --- | --- |
| `newDirectoryStream(T path, LinkOption... options)` | Opens a subdirectory relative to the open directory, returning another `SecureDirectoryStream<T>`. |
| `newByteChannel(T path, Set<? extends OpenOption> options, FileAttribute<?>... attrs)` | Opens/creates a file via a relative path and returns a `SeekableByteChannel`. |
| `deleteFile(T path)` | Deletes a file entry (also used to delete a symbolic link) relative to the current directory. |
| `deleteDirectory(T path)` | Deletes a relative directory entry, subject to corresponding directory deletion rules. |
| `move(T src, SecureDirectoryStream<T> targetDir, T target)` | Moves an entry from the open directory to an open target directory. |
| `getFileAttributeView(Class<V> type)` | Opens an attribute view of the open directory itself. |
| `getFileAttributeView(T path, Class<V> type, LinkOption... options)` | Opens an attribute view of a relative entry. |
| `close()` | Releases the open directory stream/handle. |

The type parameter `T` in Java NIO is typically `Path`. When opened from `Files.newDirectoryStream(root)`, the declared type is usually `DirectoryStream<Path>`; **do not cast immediately** without checking the instance.

## 3. Provider Support Is an Optional Feature

The `SecureDirectoryStream` API has existed since Java 7, and Java 17 includes all of the methods above. However, **the existence of the interface does not guarantee that a provider implements it**.

The Java 17 Javadoc specifies: if the implementation supports this feature, the `DirectoryStream` returned by `newDirectoryStream` may be a `SecureDirectoryStream`. Applications must inspect the actual object:

~~~java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    if (stream instanceof SecureDirectoryStream<?>) {
        System.out.println("Provider supports it at this location");
    } else {
        System.out.println("No SecureDirectoryStream");
    }
}
~~~

This is an illustrative code snippet requiring `java.nio.file.*` imports, a `root` variable, and `IOException` handling.

Actual support depends on:

- **FileSystemProvider** selected by the filesystem of the `Path` in use.
- Whether the operating system provides handle-relative open/operation primitives.
- The JDK version, provider, filesystem type, and execution environment (network-mounted filesystems, virtual filesystems, containers, etc.).

**Do not hardcode assumptions like "Linux always has it," "Windows never has it," or "ZIP filesystem definitely has it."** Actual support must be checked at runtime; providers can differ.

### 3.1. Why Not Call Methods Directly on `DirectoryStream`?

~~~java
DirectoryStream<Path> stream = Files.newDirectoryStream(root);

// Type error: DirectoryStream does not define deleteFile.
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

These are **illustrative snippets**, lacking complete resource open/close handling. The cast is appropriate in the example because `stream` is declared as `DirectoryStream<Path>`; do not extrapolate that cast to custom `DirectoryStream<T>` types with other type parameters.

### 3.2. What Should You Do If the Provider Does Not Support It?

Depending on requirements:

1. **The task requires path-race resistance as a security precondition:** *fail closed*, abort the operation, and report that the provider/environment does not meet the requirement.
2. **The directory is under exclusive control where no other actor can modify entries during processing:** ordinary `Files.*` APIs may be considered under a proven trust model.
3. **Cross-platform support is required alongside equivalent safety guarantees:** change the architecture (a dedicated staging area with strict permissions, immutable file versions, a dedicated privileged service, or a verified OS-level mechanism).

**Do not build a "fallback" by simply calling `toRealPath()`, `normalize()`, `Files.isSymbolicLink()`, then `Files.delete()` and claiming equivalence:** check-then-use still has a race window when another actor can mutate the path.

## 4. Relative Paths and Anchoring to the Directory Handle

Most importantly, secure methods normally take **paths relative to the open directory**:

~~~java
Path name = Path.of("invoice.txt");
SeekableByteChannel channel =
        secure.newByteChannel(name, Set.of(StandardOpenOption.READ));
~~~

This snippet assumes `secure` is a valid, already-open `SecureDirectoryStream<Path>`.

When `name` is a relative path, the operation uses the current directory handle; renaming a parent directory in the path namespace does not automatically redirect the handle to another directory.

**Absolute paths are an exception to avoid.** Per the Javadoc, passing an absolute path to these methods may cause lookup to follow absolute path semantics and defeat the goal of anchoring to the open directory. Reject absolute paths for operations intended to stay within a root.

### 4.1. Do Not Accept Path Traversal

Even when using a secure stream, paths outside the permitted name domain must still be rejected:

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

Checking `normalize()` and `startsWith(root)` on absolute paths **does not fully protect** against races from symbolic links or external directory modifications. A more auditable approach is restricting user input to a **single entry name**, rejecting `.`/`..`, path separators, absolute paths, special names, and cases invalid for the filesystem or application.

Illustrative validator example:

~~~java
static Path safeSingleName(FileSystem fs, String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Empty name");
    }
    Path name = fs.getPath(raw);
    if (name.isAbsolute()
            || name.getNameCount() != 1
            || name.toString().equals(".")
            || name.toString().equals("..")) {
        throw new IllegalArgumentException("Not a single entry name");
    }
    return name;
}
~~~

This is a **code snippet** requiring `java.nio.file.FileSystem` and `Path`. For internet-facing inputs, you must also define naming policies, Unicode normalization, forbidden characters, reserved names, and system-appropriate case folding. A validator does not replace authorization/ownership checks; it only narrows the set of names a user can specify.

### 4.2. Multiple Directory Levels: Traverse Step by Step With Control

If the application genuinely allows operations within nested subdirectories, open subdirectories via directory handles and control symbolic links at **every step**:

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

This is an illustrative snippet (requiring a valid `secure` variable, imports, and exception handling). `NOFOLLOW_LINKS` on `newDirectoryStream` prevents opening the subdirectory if that final entry itself is a symbolic link. Similarly, `NOFOLLOW_LINKS` in `newByteChannel`'s open options requires the operation to fail if the target entry is a symbolic link.

**Do not mix arbitrary parent traversal into a user-supplied path string** and assume it is safe just because `SecureDirectoryStream` is used. Allowed paths should be constrained and traversed component by component through trusted handles.

## 5. Symbolic Links and `NOFOLLOW_LINKS`

A common source of path races is **symbolic links**: an attacker replaces a directory entry with a link pointing outside the allowed scope.

`LinkOption.NOFOLLOW_LINKS` specifies that the target must not follow symlinks in that operation:

| Operation | Example using no-follow | Meaning |
| --- | --- | --- |
| Open subdirectory | `secure.newDirectoryStream(child, LinkOption.NOFOLLOW_LINKS)` | Fails if that entry is a symlink. |
| Open file byte channel | `secure.newByteChannel(file, Set.of(READ, LinkOption.NOFOLLOW_LINKS))` | Fails if the target file entry is a symlink. |
| Read entry metadata | `secure.getFileAttributeView(file, BasicFileAttributeView.class, LinkOption.NOFOLLOW_LINKS)` | Inspects attributes of the entry/link rather than following the symlink. |

Note that **not every method accepts `LinkOption`**: `deleteFile`, `deleteDirectory`, and `move` have their own contracts. Do not try passing `NOFOLLOW_LINKS` to `deleteFile`, as no such overload exists.

`NOFOLLOW_LINKS` does not replace restricting absolute paths or paths containing `..`. Nor does it prevent all changes caused by hard links, mounts, filesystem permissions, or another process that already opened the file earlier.

## 6. A Complete, Standalone, Safe Java 17+ Example

This example:

1. Creates a **dedicated temporary directory** and a file `message.txt` containing `HELLO`.
2. Calls `Files.newDirectoryStream(root)`.
3. If the provider supports `SecureDirectoryStream`, opens the file **by relative name** with `NOFOLLOW_LINKS`, reads its content using `SeekableByteChannel`, and then uses `deleteFile` to delete the entry.
4. If unsupported, **does not pretend to substitute a less-safe API**; the program reports refusing the secure operation.
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

Compile and run:

~~~bash
javac SecureDirectoryStreamDemo.java
java SecureDirectoryStreamDemo
~~~

If the filesystem/provider supports `SecureDirectoryStream` and temporary files work normally, stdout:

~~~text
mode=SECURE
text=HELLO
deleted=true
~~~

If the provider **does not** support it, stdout:

~~~text
mode=UNAVAILABLE
action=REFUSED
~~~

The two outputs above are **two environment-dependent conditional branches**, not a single fixed outcome across all OSes/JDKs. If filesystem operations lack permissions or encounter an I/O error, the program may throw `IOException` instead of printing either branch completely; that is the right behavior when a security operation fails.

### 6.1. Why Check `instanceof` Instead of Checking the OS?

`Files.newDirectoryStream(root)` has declared return type `DirectoryStream<Path>`. If the actual object implements `SecureDirectoryStream`, the additional API can be used. Support depends on both OS and provider, so checking the actual runtime type is **more accurate** than relying on an OS name or filesystem label from configuration.

### 6.2. Why Read Through `SeekableByteChannel`?

`secure.newByteChannel(...)` binds opening the file to the directory handle, avoiding calling `Files.newInputStream(root.resolve(name))` (which could re-resolve the path). `Channels.newInputStream(channel)` merely wraps the **already-opened channel**, so it does not change the underlying file object bound to that handle.

`newByteChannel` returns a channel with a lifetime independent of the directory stream that opened it; however, the example keeps the stream open until `deleteFile` completes so the directory handle remains available for deletion.

### 6.3. Why Clean Up With `Files.deleteIfExists` at the End?

The `finally` block handles a **temporary directory created and owned by the program itself**, after the secure operations have finished. It is test cleanup logic, **not an equivalent security fallback** if handling a directory controlled by an attacker. If the temporary root were controlled by an untrusted actor, the safety assumptions of the example would need to be re-evaluated.

## 7. Opening Files With `newByteChannel`

Java 17 signature:

~~~java
SeekableByteChannel newByteChannel(
        T path,
        Set<? extends OpenOption> options,
        FileAttribute<?>... attrs
) throws IOException;
~~~

This is a **method signature**, not a code block that can be pasted directly inside `main`.

Commonly used options:

- `StandardOpenOption.READ`: read.
- `StandardOpenOption.WRITE`: write.
- `StandardOpenOption.CREATE_NEW`: create only if the file does not exist; useful to avoid overwriting an existing entry.
- `StandardOpenOption.CREATE`: create if absent, without rejecting an existing entry; consider carefully with untrusted files.
- `StandardOpenOption.TRUNCATE_EXISTING`: truncates an existing file when opened for writing, dangerous if the target has not been properly validated.
- `LinkOption.NOFOLLOW_LINKS`: reject if the final path entry is a symbolic link.

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

This is an illustrative snippet requiring `ByteBuffer`, `StandardCharsets`, and related API imports. `CREATE_NEW` avoids overwriting an existing entry, though it does not imply user input is authorized under business rules to create that name. Validate names/permissions and enforce byte limits.

The `FileAttribute<?>... attrs` parameter can be used to set attributes atomically at file creation **when supported by the provider**; unsupported attributes may throw `UnsupportedOperationException`. Do not assume every provider accepts POSIX attributes.

## 8. Deleting Files, Symlinks, and Directories

`secure.deleteFile(relativeName)` deletes a file **entry** relative to the directory stream; if the entry is a symbolic link, behavior is defined on the link entry itself rather than deleting the link's target. `secure.deleteDirectory(relativeName)` deletes a directory entry under filesystem contracts, not as a "recursive tree delete."

~~~java
secure.deleteFile(Path.of("obsolete.tmp"));
secure.deleteDirectory(Path.of("empty-folder"));
~~~

This is an illustrative snippet: both names must be valid within the directory handle and the provider must have delete permission; the directory must satisfy filesystem deletion rules (typically empty). Errors such as `NoSuchFileException`, `DirectoryNotEmptyException`, `AccessDeniedException`, or `IOException` must be handled per business logic.

**Risks outside the scope of secure streams:** if an attacker has permission to modify contents inside an already-opened file or create hard links to a file, directory-relative APIs do not by themselves guarantee the content is trustworthy. `SecureDirectoryStream` mainly serves **locating files in a directory tree when names can be swapped**, not replacing the permission system.

### 8.1. Deleting Directory Trees Can Be More Complex

To delete an entire tree that an attacker might concurrently mutate, do not simply list entries with `Files.walk(root)` and call `Files.delete(path)` on absolute paths. You need a strategy that operates relatively using directory handles at each level, avoids following symlinks, checks permissions, and bounds depth/entry count. In environments not supporting `SecureDirectoryStream`, **do not claim** an equivalent recursive deletion shares the same TOCTOU resistance.

## 9. `move()`: Moving Between Two Open Directories

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

This is an illustrative snippet where `secure` points to the source directory containing a valid `archive` subdirectory.

Per the Java 17 Javadoc, `move` behaves like `Files.move` with `ATOMIC_MOVE`: the move is performed as an atomic filesystem operation. However:

- The provider may throw `AtomicMoveNotSupportedException` when an atomic move cannot be performed.
- If the target already exists, whether it replaces or fails is **implementation-specific**.
- There is no `REPLACE_EXISTING` parameter on this `SecureDirectoryStream.move` method; do not assume an overwrite policy.
- `srcpath` and `targetpath` should be constrained to **relative paths** within trusted directories. Using absolute paths may bypass the intended directory-handle semantics.
- Atomic rename does not replace data validation, permission checks, durability of changes, or a power-loss-recoverable version publishing workflow.

## 10. Reading Metadata Safely via Directory Handle

`getFileAttributeView` lets you read/update file information without rebuilding an absolute path by name:

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

This is an illustrative snippet requiring `java.nio.file.attribute.BasicFileAttributeView` and `BasicFileAttributes`. Depending on the provider, an attribute view may be unsupported and return `null`. Beyond `BasicFileAttributeView`, some providers support specialized attribute views, but do not assume identical support across filesystems.

`NOFOLLOW_LINKS` targets the metadata of the final entry rather than the link target. Although a secure directory handle reduces *entry-location* races, metadata is still a **point-in-time snapshot**: another writer can alter the file's content or metadata after reading. For payload/ACL/version consistency, additional strategies such as immutable files, exclusive ownership, or synchronization protocols are needed.

### 10.1. Attribute View of the Directory Itself

~~~java
BasicFileAttributeView dirView =
        secure.getFileAttributeView(BasicFileAttributeView.class);
BasicFileAttributes dirAttrs = dirView.readAttributes();
~~~

This is an illustrative snippet; if the provider does not support the requested view it can return `null`, so production code must check before dereferencing.

The benefit of a view from an open directory is avoiding re-resolving a mutable path name. Still, it does not turn every attribute read into an atomic transaction with other program operations.

## 11. `SecureDirectoryStream` Is Not a Complete Sandbox

What the interface aims to provide:

- Processing relative paths against an **open directory** rather than a mutable name string.
- Descending into subdirectories via a new **secure directory handle**, optionally with `NOFOLLOW_LINKS`.
- Opening file byte channels, deleting, and moving entries with semantics that help mitigate path races.
- Obtaining attribute views tied to a directory handle to reduce check-then-use reliance on global path names.

What it **does not automatically guarantee**:

1. **Does not provide per-user authorization:** the application still must verify which user may read/delete which file.
2. **Does not block all hard links:** a non-symlink entry can still point to an inode the application should not touch; permissions and filesystem policies remain essential.
3. **Does not lock file contents against other writers:** opening a channel to the right file does not mean bytes cannot be modified concurrently.
4. **Does not completely prevent mount/namespace changes:** the security model depends on the OS and attacker privileges; evaluate the specific threat model.
5. **Does not eliminate all TOCTOU outside filesystem operations:** metadata verification, format parsing, checksum validation, and business decisions are separate steps.
6. **Does not automatically resolve symlinks in a given path if you do not control the structure:** traverse level by level and apply `NOFOLLOW_LINKS` in the right places.
7. **Does not guarantee all providers support it:** check the actual object and handle the unsupported branch.
8. **Does not replace TLS, digital signatures, or data validation:** a "properly located" path does not mean the data is trustworthy.

A secure system must clearly define OS permissions, who can modify directories and entries, which data is user-supplied, which provider actually runs, and the consequences when an operation fails.

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

The `incoming` directory could be swapped to a symlink between the two calls; this is an **unsafe illustrative snippet in untrusted environments**.

With a secure stream, given an already-trusted handle to `root`:

~~~java
try (SecureDirectoryStream<Path> incoming =
        rootSecure.newDirectoryStream(
                Path.of("incoming"), LinkOption.NOFOLLOW_LINKS)) {
    // Work relative to the opened directory itself.
}
~~~

Note that **initially obtaining `rootSecure`** must also come from a trusted root source and proper protections. If an attacker can swap `root` between choosing `root` and `Files.newDirectoryStream(root)` opening it, the resulting secure stream anchors to whatever directory **was actually opened**, which may not be the directory intended by business policy.

### 12.2. Mistake: Check Symlink Then Open Normally

~~~java
if (!Files.isSymbolicLink(file)) {
    Files.newInputStream(file); // Another name may appear after the check.
}
~~~

**Risky illustrative code.** When using `SecureDirectoryStream.newByteChannel(relativeName, Set.of(READ, NOFOLLOW_LINKS))`, follow-link control is specified directly in the directory-handle-relative open operation, avoiding that check-then-open gap for the final entry.

### 12.3. Mistake: Ignoring the Unsupported Case

~~~java
DirectoryStream<Path> ds = Files.newDirectoryStream(root);
SecureDirectoryStream<Path> s =
        (SecureDirectoryStream<Path>) ds; // May throw ClassCastException.
~~~

A program that runs on machine A is not guaranteed to be safe or even work on machine B. Check `instanceof` and provide an explicit fail-closed branch. Never "catch `ClassCastException` and fall back to `Files.delete`" when the original risk was a symlink/path race.

## 13. Lifecycle and Exception Handling Details

### 13.1. Closing Directory Streams on Time

Both `DirectoryStream` and `SecureDirectoryStream` implement `Closeable`, so:

~~~java
try (DirectoryStream<Path> stream = Files.newDirectoryStream(root)) {
    // Check instanceof and operate here.
}
~~~

Closing a stream releases associated resources; secure-relative methods called on a closed stream may throw `ClosedDirectoryStreamException`. A child `SecureDirectoryStream` opened from a parent stream **has its own independent lifecycle** by contract: closing the parent does not automatically close the child. Similarly, channels opened via `newByteChannel` must be closed independently.

Therefore directory handle and file handle lifetimes can be decoupled, but production code should keep ownership explicit to prevent descriptor leaks.

### 13.2. Errors That May Need Handling

| Error / exception | Situation |
| --- | --- |
| `NoSuchFileException` | Entry no longer exists when accessed. |
| `AccessDeniedException` | Permissions do not allow the operation. |
| `NotDirectoryException` | Name requested to open as a directory is not a directory (provider-dependent). |
| `DirectoryNotEmptyException` | Deleting a directory that still has entries. |
| `ClosedDirectoryStreamException` | Calling a secure operation after the directory stream is closed. |
| `AtomicMoveNotSupportedException` | Unable to perform `move` as an atomic operation. |
| `UnsupportedOperationException` | Provider does not support the requested option or attribute. |
| `IOException` | Broader I/O error (including races causing a target to vanish). |

Do not assume every OS returns the exact same **specific exception subclass** in every situation; many fine-grained exception classes are *optional specific exceptions*. When a security operation cannot complete as required, abort or roll back the workflow appropriately rather than silently ignoring it.

### 13.3. Thread-Safety and Iteration

A directory stream iterates over entry names; the set of entries can change during iteration. Do not rely on iteration order, do not assume a snapshot, and do not use streams or channels across threads in a data-race-prone manner. When asynchronous processing is needed, define which thread owns the directory handle and manage when it closes.

## 14. A Safer Workflow for Handling File Uploads

Example service receiving a filename from a request and storing it in an upload directory:

1. **Authenticate and authorize** the user first, and limit upload count and size.
2. Select the root from trusted configuration; never take an absolute path from the user.
3. Open the root and **check `instanceof SecureDirectoryStream<?>`**; if unsupported by the provider and path-race resistance is mandatory, reject the operation.
4. Constrain the filename to a **single relative component**; forbid absolute paths, `.`, `..`, and separator representations.
5. Use `newByteChannel(name, Set.of(WRITE, CREATE_NEW, NOFOLLOW_LINKS))` to create the entry, avoiding overwrites and following symlinks.
6. Write data while counting bytes, checking quotas and size limits; handle partial writes as needed.
7. If the upload requires a controlled commit, store in a trusted staging area, validate content, and use a designed publishing workflow. Secure-relative `move` has atomic semantics but does not automatically add durability or authorization guarantees.
8. Close channels and directory streams within proper lifetimes and clean up temporary artifacts on error, while still accounting for races and ownership during cleanup.
9. Log provider-unsupported, permission, size/quota, and rejection errors without leaking sensitive paths to the client.

Do not treat `CREATE_NEW` as a guarantee that "since we created this file, it is definitely safe": its content may come from an untrusted source, names may collide at business level, and many other security requirements remain.

## 15. When Should You Still Use Ordinary `Files.*`?

`Files.readString`, `Files.copy`, `Files.delete`, `Files.move`, and `Files.walkFileTree` provide very convenient APIs. They do not automatically become wrong just because `SecureDirectoryStream` exists.

Choose `Files.*` when:

- Files/directories are owned by the application with **protective OS permissions**, and no untrusted actor can swap paths between operations.
- Reading immutable config files, internal build data, test fixtures, or batch jobs with no meaningful path-race threat model.
- The provider does not support secure streams, yet the workflow **is proven not to require** race protection between check and use.

Choose `SecureDirectoryStream` when:

- Deleting/moving/reading/writing in a shared directory where an untrusted actor could concurrently modify entries.
- Protecting against symlink swaps of directory components controlled by an adversary.
- Traversing file trees or publishing entries via directory handles with TOCTOU mitigation requirements.
- You can **require the environment to support this API** or enforce a fail-closed policy.

If path-race protection is mandatory and the platform lacks equivalent capability, the right decision may be **not deploying that feature on that platform**, rather than silently weakening guarantees.

## 16. Self-Check Exercises

1. **Is `SecureDirectoryStream` a class or an interface?** It is an interface extending `DirectoryStream<T>`.
2. **Does every `Files.newDirectoryStream(dir)` return a `SecureDirectoryStream`?** No; it depends on provider and OS support.
3. **How do you check support?** Check whether the actual object is `instanceof SecureDirectoryStream<?>`; cast only when valid.
4. **Why can `Files.isSymbolicLink(path)` followed by `Files.newInputStream(path)` be dangerous?** There is a TOCTOU window between checking and using the name.
5. **What is the benefit of paths relative to a directory handle?** It avoids re-resolving global directory names when entries are renamed or swapped.
6. **What is the role of `NOFOLLOW_LINKS`?** Requests not following symbolic links in that operation, such as opening subdirectories or files.
7. **Does `deleteFile` take a `NOFOLLOW_LINKS` parameter?** No; it has its own entry-deletion contract.
8. **Does secure stream `move` guarantee overwriting an existing target?** No; when the target exists, replacing vs failing is implementation-specific.
9. **What can `move` throw if atomic move is unavailable?** `AtomicMoveNotSupportedException`.
10. **Does closing a parent secure directory stream automatically close child streams?** No. Child streams have their own lifetimes.
11. **Does closing a directory stream automatically close channels opened from it?** No. Channels have their own lifetimes.
12. **If the provider does not support it, may you claim a check-then-delete fallback gives the same guarantee?** No; if race protection is mandatory, fail closed or change the architecture.
13. **Is passing `../../etc/passwd` as a relative path safe just because a secure stream is used?** No; validation and path-component controls are still required.
14. **Does `SecureDirectoryStream` prevent all hard-link attacks?** No; ownership, permissions, and filesystem threat models must still be evaluated.
15. **If a file is opened safely, yet another writer can alter its contents, is the data automatically immutable?** No; version/ownership controls and consistent read/write protocols are needed.
16. **If a program runs on Linux using a custom `FileSystemProvider` that does not support SDS, can it be used?** Never assume; check at runtime and handle unsupported.
17. **Should you pass an absolute path to `secure.newByteChannel(...)` to stay inside root?** No; absolute paths can bypass anchoring to the open directory.
18. **If an app needs path-race protection without controlling the initial root, does opening SDS prove the directory is right?** Not yet; the initial root handle must point to a trusted directory.
19. **Does every `DirectoryStream` iteration reflect an immutable snapshot?** No; entries can change during iteration.
20. **Does `SecureDirectoryStream` replace upload content validation and quotas?** No; it focuses on relative path operations, not data validation.

## 17. Official Java 17 Documentation

- [SecureDirectoryStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): open-directory-relative semantics, supported methods, fallback, and exceptions.
- [DirectoryStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/DirectoryStream.html): iteration and directory stream lifecycle.
- [Files — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `newDirectoryStream`, `newByteChannel`, and regular file operations.
- [LinkOption — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html): `NOFOLLOW_LINKS` and per-operation meaning.
- [FileSystemProvider — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html): provider's role in filesystem implementation.

**Remember:** `SecureDirectoryStream` operates relative to an **open directory handle**, helping resist many entry/link-swap races when working with **relative paths**. Support depends on the provider and OS, so you must **check `instanceof` at runtime**. If race safety is mandatory and the provider lacks support, **fail closed**—do not substitute check-then-use and claim equivalence. Always control path names, symlinks, access permissions, lifetimes, and data integrity.
