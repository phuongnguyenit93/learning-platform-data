# Size, File Type, and `fileKey` with `BasicFileAttributes` in Java NIO.2

When working with files in Java, a path (`Path`) does not by itself tell you whether what it points to is a **regular file**, **directory**, **symbolic link**, special filesystem object, or non-existent. Applications also need to know **size in bytes**, and sometimes need to determine whether two paths represent **the same actual file**. These questions are related but not identical.

The central API is:

```java
BasicFileAttributes attributes = Files.readAttributes(
        path, BasicFileAttributes.class);
```

This is an **illustrative** snippet requiring imports for `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.attribute.BasicFileAttributes`, and `IOException` handling. The call reads attributes from the filesystem through the provider; it **does not read file contents** into a `String`, does not open an `InputStream` to read content bytes, and does not create a new file.

From `attributes`, you can query:

```java
long bytes = attributes.size();
boolean regular = attributes.isRegularFile();
boolean directory = attributes.isDirectory();
boolean symbolicLink = attributes.isSymbolicLink();
boolean other = attributes.isOther();
Object key = attributes.fileKey();
```

Among these methods, `size()` and the four classification predicates return attribute info; `fileKey()` provides an **object identifier determined by the filesystem/provider** if supported. `fileKey` is very useful, yet it is **not a global ID, not guaranteed to exist, and not an immutable security proof**.

This lesson uses Java 17+, focusing on API contract semantics, `File`/`Files` differences, behavior with symbolic links, mutable filesystem metadata, file identity checks, and practical pitfalls.

## 1. `BasicFileAttributes` and `Files.readAttributes(...)`

`BasicFileAttributes` is an interface in the package:

```java
java.nio.file.attribute.BasicFileAttributes
```

It provides the basic metadata group:

| Member | Value | Question It Answers |
| --- | --- | --- |
| `size()` | `long` | Size reported by the filesystem, in bytes |
| `isRegularFile()` | `boolean` | Is this a regular file? |
| `isDirectory()` | `boolean` | Is this a directory? |
| `isSymbolicLink()` | `boolean` | Is this a symbolic link? |
| `isOther()` | `boolean` | Does this belong to another type besides those listed above? |
| `fileKey()` | `Object` or `null` | Is there a file identifier key supplied by the provider? |
| `creationTime()` | `FileTime` | Creation time (provider-dependent) |
| `lastModifiedTime()` | `FileTime` | Last modification time |
| `lastAccessTime()` | `FileTime` | Last access time |

The three timestamps are other parts of `BasicFileAttributes`, though the focus here is **size, type, fileKey**. Do not assume every provider has the same timestamp precision or supports full metadata across all filesystem types.

A typical attribute-reading call:

```java
BasicFileAttributes attrs = Files.readAttributes(
        path, BasicFileAttributes.class);
```

By default, the query typically **follows symbolic links** to retrieve attributes of the *link target*. If you want to ask about **the symbolic link entry itself**, use:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        path,
        BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

These are **illustrative** snippets, not standalone Java programs. `LinkOption.NOFOLLOW_LINKS` matters because the same `Path` can lead to two different metadata subjects: **the link** or **the target**.

### Why Read an Attribute Group Instead of Calling Multiple Methods?

You could call:

```java
long bytes = Files.size(path);
boolean regular = Files.isRegularFile(path);
```

If you need file type, size, and `fileKey` together, `Files.readAttributes(...)` bundles the basic attributes into **one API-level query**. It also provides results from the same returned attribute set.

However, **do not assume all attributes are read atomically** on every filesystem; the API contract leaves the exact reading mechanism to the implementation. Furthermore, fetched attributes can become stale immediately after the call. `BasicFileAttributes` is not a file "lock" and does not guarantee unchanged state for subsequent operations.

## 2. `size()` Is Size in Bytes, Not Characters

For a regular file, `attrs.size()` represents **the file size in bytes** reported by the filesystem; the value has type `long`. `Files.size(path)` also returns the byte size and can throw `IOException` if it cannot be retrieved.

Three units are often confused:

- **Bytes in the file**: the value from `Files.size(path)` or `attrs.size()` for a regular file.
- **UTF-16 `char` units**: `String.length()` in Java, not the UTF-8 byte count.
- **Unicode code points**: the count of Unicode code points in a string, which also does not necessarily equal bytes or `String.length()`.

For example, the string `"A😀"` when encoded in UTF-8:

| Unit | Result |
| --- | ---: |
| UTF-8 bytes | 5 |
| `String.length()` | 3 |
| `String.codePointCount(...)` | 2 |

The character `A` takes 1 UTF-8 byte; the emoji in the example takes 4 bytes. The emoji takes **two UTF-16 code units** in Java, so the string has `length()==3`.

### Example 1 — Observing size, type, and fileKey

The program creates a temporary file on the current machine, writes UTF-8, and reads that file's attributes. The checks do not depend on absolute paths or temporary file names.

```java
// BasicAttributesDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class BasicAttributesDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("attrs-", ".txt");
        String text = "A😀";

        try {
            Files.writeString(path, text, StandardCharsets.UTF_8);

            BasicFileAttributes attrs = Files.readAttributes(
                    path, BasicFileAttributes.class);

            System.out.println("regular=" + attrs.isRegularFile());
            System.out.println("directory=" + attrs.isDirectory());
            System.out.println("symbolicLink=" + attrs.isSymbolicLink());
            System.out.println("other=" + attrs.isOther());
            System.out.println("size=" + attrs.size());
            System.out.println("filesSize=" + Files.size(path));
            System.out.println("utf16Units=" + text.length());
            System.out.println("codePoints="
                    + text.codePointCount(0, text.length()));
            System.out.println("fileKeyAvailable="
                    + (attrs.fileKey() != null));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 BasicAttributesDemo.java
java BasicAttributesDemo
```

On a typical temporary filesystem with a regular file where writing succeeds, the first lines are:

```text
regular=true
directory=false
symbolicLink=false
other=false
size=5
filesSize=5
utf16Units=3
codePoints=2
```

The last line is **filesystem/provider-dependent**:

```text
fileKeyAvailable=true
```

or:

```text
fileKeyAvailable=false
```

The actual `fileKey` contents are not printed in the sample output because its type, format, and availability are **not fixed** across Windows, Linux, macOS, and other filesystems.

The `Files.writeString(...)` call in the example uses default options to write content. After it completes, `attrs.size()` and `Files.size(path)` can both report 5 bytes. In an application with multiple processes accessing the file, these two queries could still observe different results if data changes in between.

## 3. `size()` Is Not "Disk Space Occupied"

Distinguish:

- **Logical file size**: the byte length of file content seen by the application; typically the result of `size()`.
- **Allocated space**: the actual blocks/extents allocated by the filesystem on the device, which can differ from logical size.
- **Volume capacity**: total, free, or usable space of a partition, not the size of a single file.

For example, a small 1-byte file can still occupy one block on the filesystem; a very large **sparse file** might only allocate blocks in certain regions; a filesystem-compressed file can physically occupy less space than its logical size.

`Files.size(path)` and `BasicFileAttributes.size()` are **not APIs for accurately measuring physical allocated space**. Do not use them to deduce occupied blocks, nor to infer the memory needed for every decompression/compression variant from that value.

In addition:

- **Directories:** the size reported by `size()` for a directory is **implementation-specific, not consistently specified**. It does not mean the total size of all child files.
- **Symbolic links:** if reading attributes of **the link itself** (`NOFOLLOW_LINKS`), the meaning of `size()` depends on the provider, such as the length of the link path representation; do not treat it as the target's size.
- **Sockets, devices, FIFOs, or other types:** the meaning of `size()` can vary by system; do not blindly apply regular-file rules.
- **Empty files vs. non-existent files:** an empty regular file has size 0; a non-existent path **has no valid attribute set** for `Files.readAttributes` to return normally.

If you need the total size of a **directory tree**, you must traverse the tree with an appropriate API and define your own rules: whether to count links, whether to cross mounts, whether to count duplicate hard links, and how to handle permissions and disappearing files. Do not use `Files.size(directory)` to replace that operation.

## 4. Classifying Files with the Four Type Flags

`BasicFileAttributes` classifies according to different questions:

| Flag | Meaning |
| --- | --- |
| `isRegularFile()` | Regular file, whose content is managed as a regular file |
| `isDirectory()` | Directory |
| `isSymbolicLink()` | Symbolic link |
| `isOther()` | Another file type not falling into the three types listed |

Do not write:

```java
if (!attrs.isRegularFile()) {
    // Wrong if you assume by default this is definitely a directory!
}
```

An object that is not a regular file could be a symbolic link, device, FIFO, socket, or another file type. If you read metadata **while following links**, the `isSymbolicLink()` flag can be `false` because the object you are observing is the **target** (e.g., a regular file). When you want to classify the link entry, you must read with `NOFOLLOW_LINKS`.

`isOther()` **does not mean the file does not exist**. If `Files.readAttributes` cannot fetch attributes because the path does not exist, it normally throws `NoSuchFileException`/`IOException`, rather than creating a `BasicFileAttributes` with `isOther()==true`.

### Example 2 — Distinguishing regular file, directory, and missing-file error

```java
// FileTypeAttributesDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class FileTypeAttributesDemo {
    private static void inspect(String name, Path path)
            throws java.io.IOException {
        try {
            BasicFileAttributes attrs =
                    Files.readAttributes(path, BasicFileAttributes.class);
            System.out.println(name + ":regular="
                    + attrs.isRegularFile() + ",directory="
                    + attrs.isDirectory());
        } catch (NoSuchFileException ex) {
            System.out.println(name + ":missing");
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("kinds-");
        Path regular = root.resolve("file.txt");
        Path folder = root.resolve("folder");
        Path missing = root.resolve("missing.txt");

        try {
            Files.writeString(regular, "OK", StandardCharsets.UTF_8);
            Files.createDirectory(folder);

            inspect("file", regular);
            inspect("folder", folder);
            inspect("absent", missing);
        } finally {
            Files.deleteIfExists(regular);
            Files.deleteIfExists(folder);
            Files.deleteIfExists(root);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 FileTypeAttributesDemo.java
java FileTypeAttributesDemo
```

Output on a common temporary filesystem, when creating the file/directory succeeds:

```text
file:regular=true,directory=false
folder:regular=false,directory=true
absent:missing
```

Unlike `java.io.File.isFile()`/`isDirectory()`, which typically return `false` when undetermined, `Files.readAttributes()` can indicate **the failure reason via `IOException`**. However, not every provider classifies errors as exact `NoSuchFileException`; for instance, another form of `IOException` might still be thrown and propagated to the caller.

## 5. `Files.size()`, `File.length()`, and `BasicFileAttributes.size()`

There are three common APIs for finding size:

| Approach | Return Type | Notable Behavior |
| --- | --- | --- |
| `new File(pathString).length()` | `long` | Legacy API; non-existent file usually returns `0`; value for directories is unspecified |
| `Files.size(path)` | `long` | NIO.2 API, throws `IOException` when query fails |
| `Files.readAttributes(path, BasicFileAttributes.class).size()` | `long` | Fetches size along with type/`fileKey` attributes, can throw `IOException` |

Because an empty file also has size `0`, do not use the condition:

```java
if (legacyFile.length() == 0) {
    // Concluding "empty file" misses other conditions.
}
```

This snippet illustrates a mistake: the file might not exist, might be a directory, might have a query error, or might genuinely be an empty regular file.

There is also no way to guarantee a file hasn't changed using a sequence like:

```java
if (Files.exists(path) && Files.isRegularFile(path)) {
    long size = Files.size(path);
    // The file may have changed between calls.
}
```

Checking first and using later has **TOCTOU** (*time of check to time of use*). Always handle errors on the actual query or file open. If processing must read a consistent version, you need snapshots, locks, or specific filesystem capabilities, not just the three booleans above.

## 6. What Exactly Is `fileKey()`?

Per the `BasicFileAttributes` contract, `fileKey()` returns an `Object` **identifying the file** according to the mechanism provided by the filesystem/provider, or `null` if no identifier key is available.

```java
Object key = attrs.fileKey();

if (key == null) {
    // The provider does not supply a file key in this case.
}
```

This is an **illustrative snippet**; `attrs` is an existing `BasicFileAttributes`. The type is `Object`, not a mandatory `long`, `UUID`, or `String`. Do not cast it to `Long` or guess its printed syntax. On one filesystem, the key might be implemented using an inode number combined with a device identifier; elsewhere it might use a file ID or custom structure; the implementation decides its shape.

### Uses

`fileKey` is useful when you need to:

- Record the **provider-supplied identity** of a file during a scan or operation.
- Detect **the same file object** appearing through multiple paths, such as hard links (when the provider supports file keys).
- Support tree-traversal algorithms and recognize already-visited objects in scenarios involving symbolic links, combined with fallback mechanisms when no key exists.
- Compare metadata **within the provider's stability scope**, such as detecting that a path now points to a different object after being replaced.

However, you must respect its limitations.

### Limitations to Remember

1. **May be `null`.** Never assume a key is always present.
2. **Not a global ID.** A file key is only meaningful within the scope of the corresponding filesystem/provider; two filesystems may produce similar-looking values.
3. **Not guaranteed to persist forever.** Deleting a file can release its ID for reuse by the filesystem; do not use the key as a long-term record identifier.
4. **Not tied to the path string.** Renaming within the same filesystem can preserve file identity; replacing a different file at the same pathname can change `fileKey`.
5. **Does not prove file content hasn't changed.** A file can be rewritten while its key still belongs to the same object.
6. **Not an authorization token.** `fileKey` cannot replace authentication, authorization, or protected file handles.
7. **Do not rely on `key.toString()` as a portable format.** The printed format is an implementation detail.
8. **Not sufficient to prevent races.** After retrieving the key, the entry at the path could be replaced by a concurrent operation.

**Distinguish `fileKey` from a content hash**: the key identifies the filesystem-provided object; SHA-256 (for example) identifies the hash of **the content that was read**. Two different files can share identical content and hashes; the same file can change content over time while its key stays unchanged. Do not use the key to infer that two files have identical data.

## 7. `Path.equals()`, `Files.isSameFile()`, and `fileKey()` Differ

Three questions are often mixed up:

| API | Question | Does It Necessarily Access the Filesystem? |
| --- | --- | --- |
| `pathA.equals(pathB)` | Are the two path objects equal per provider rules? | Not used as a file identity check |
| `Files.isSameFile(pathA, pathB)` | Do the two paths currently identify **the same file**? | May query the filesystem, may throw `IOException` |
| `attrsA.fileKey()` and `attrsB.fileKey()` | Does the provider supply identifier keys and can two keys be compared? | Keys were fetched from metadata reads; provides no immutability |

Example:

```text
/data/report.txt
/data/aliases/current.txt  --(symbolic link)-->  /data/report.txt
/data/backup-hardlink.txt  --(hard link)------>  same file object
```

Two `Path`s with different strings **can** still represent the same actual file. On filesystems supporting hard links, two names pointing to the same file object may have the same `fileKey`. A symbolic link **when followed** can lead to the same object and same key as the target; **when using `NOFOLLOW_LINKS`**, you are fetching attributes and key of **the link itself**, not the target.

`Files.isSameFile(...)` is usually the more appropriate API to ask "do these two paths point to the same file?". If two `Path` objects are **equal per `equals`**, the implementation is allowed/contracted to return `true` immediately without checking whether the actual file exists. Therefore, do not use `Files.isSameFile(p, p)` to verify that `p` definitely exists; checking actual existence requires another appropriate operation.

### Example 3 — file key, hard links, and file identity

The following program attempts to create a **hard link** to a temporary file. Because not all filesystems allow creating hard links, the program has two separately explained branches; it does not assume `fileKey()` always has a value.

```java
// FileKeyIdentityDemo.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class FileKeyIdentityDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("key-demo-");
        Path original = directory.resolve("original.txt");
        Path alias = directory.resolve("alias.txt");

        try {
            Files.writeString(original, "same object",
                    StandardCharsets.UTF_8);

            BasicFileAttributes first = Files.readAttributes(
                    original, BasicFileAttributes.class);

            System.out.println("fileKeyAvailable="
                    + (first.fileKey() != null));

            try {
                Files.createLink(alias, original);

                BasicFileAttributes second = Files.readAttributes(
                        alias, BasicFileAttributes.class);

                System.out.println("sameFile="
                        + Files.isSameFile(original, alias));

                if (first.fileKey() != null
                        && second.fileKey() != null) {
                    System.out.println("keyEqual="
                            + first.fileKey().equals(second.fileKey()));
                } else {
                    System.out.println("keyEqual=unavailable");
                }
            } catch (IOException | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("hardLinkDemo=unavailable");
            }
        } finally {
            Files.deleteIfExists(alias);
            Files.deleteIfExists(original);
            Files.deleteIfExists(directory);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 FileKeyIdentityDemo.java
java FileKeyIdentityDemo
```

The output is **platform-dependent**. On a filesystem supporting hard links, when all operations succeed, stdout looks like:

```text
fileKeyAvailable=true
sameFile=true
keyEqual=true
```

On a system where `fileKey` is `null` yet hard links are still supported, this branch might be:

```text
fileKeyAvailable=false
sameFile=true
keyEqual=unavailable
```

If the environment does not support or denies creating hard links:

```text
fileKeyAvailable=true
hardLinkDemo=unavailable
```

The value of `fileKeyAvailable` in the last branch can also be `false`. The result is **not a fixed stdout guarantee across every machine**. The program deliberately does not print the `fileKey` object because its internal format and meaning are not portable.

When two hard-link names point to the same file, `Files.isSameFile()` is appropriate for checking current identity. Comparing two read keys is supporting information when both are non-null and on the same filesystem, yet it does not replace error handling or the risk of the file changing during the check.

## 8. Symbolic Links: Reading Link Attributes or Target Attributes?

This is the key point for `isSymbolicLink()` and `fileKey()`.

Suppose:

```text
report.txt                 (regular file)
report-link.txt ----------> report.txt   (symbolic link)
```

Two different ways to read:

```java
// Follow link: observe target attributes.
BasicFileAttributes targetAttrs = Files.readAttributes(
        link, BasicFileAttributes.class);

// Do not follow link: observe the symbolic link itself.
BasicFileAttributes linkAttrs = Files.readAttributes(
        link, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);
```

This is an illustrative snippet with a declared `Path` named `link`; import `LinkOption` along with the other classes.

If the target is a regular file:

- `targetAttrs.isRegularFile()` is typically `true`.
- `targetAttrs.isSymbolicLink()` is typically `false`, because you are viewing **the target**.
- `linkAttrs.isSymbolicLink()` is `true` when the provider recognizes links.
- `targetAttrs.size()` corresponds to the regular target (when determinable).
- `linkAttrs.size()` is an attribute of **the link** and should not be assumed equal to the target's size.
- `fileKey` can distinguish the link object from the target object, if the provider supplies keys.

### Example 4 — observing `NOFOLLOW_LINKS`, including broken links

This program **attempts** to create a relative symlink in a temporary directory. Some Windows environments require specific privileges/features, and some providers do not support symlinks; in those cases, the program reports unavailable instead of asserting the feature exists on every machine.

```java
// SymbolicLinkAttributesDemo.java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class SymbolicLinkAttributesDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("link-attrs-");
        Path target = dir.resolve("original.txt");
        Path link = dir.resolve("shortcut.txt");

        try {
            Files.writeString(target, "OK", StandardCharsets.UTF_8);

            try {
                Files.createSymbolicLink(
                        link, target.getFileName());

                BasicFileAttributes followed = Files.readAttributes(
                        link, BasicFileAttributes.class);
                BasicFileAttributes notFollowed = Files.readAttributes(
                        link, BasicFileAttributes.class,
                        LinkOption.NOFOLLOW_LINKS);

                System.out.println("followRegular="
                        + followed.isRegularFile());
                System.out.println("nofollowSymbolic="
                        + notFollowed.isSymbolicLink());

                Files.delete(target);

                System.out.println("brokenTargetExists="
                        + Files.exists(link));
                System.out.println("linkEntryExists="
                        + Files.exists(
                                link, LinkOption.NOFOLLOW_LINKS));
            } catch (IOException | UnsupportedOperationException
                     | SecurityException ex) {
                System.out.println("symlinkDemo=unavailable");
            }
        } finally {
            Files.deleteIfExists(link);
            Files.deleteIfExists(target);
            Files.deleteIfExists(dir);
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SymbolicLinkAttributesDemo.java
java SymbolicLinkAttributesDemo
```

On a system that supports symbolic links and executes every step successfully, stdout is:

```text
followRegular=true
nofollowSymbolic=true
brokenTargetExists=false
linkEntryExists=true
```

If creating/querying the link fails, the program may print:

```text
symlinkDemo=unavailable
```

This is an example **with system-dependent output**. After the target is deleted, `Files.exists(link)` (which normally follows links) does not find the target, while `Files.exists(link, NOFOLLOW_LINKS)` can still confirm the symlink entry remains. Do not treat `Files.exists(link)==false` as sufficient proof that the link itself has disappeared.

When a library needs a "do not follow symbolic links" rule, pass the appropriate option to **the supporting operation itself** and understand the provider's behavior. Checking beforehand with `NOFOLLOW_LINKS` does not automatically protect a subsequent open operation from concurrent changes (TOCTOU).

## 9. `fileKey` After Rename, Replace, Delete, and Recreate

A pathname is not an immutable identity of an object. Scenarios include:

| Operation | Pathname | What Can Happen to File Object / Key? |
| --- | --- | --- |
| Overwrite content in the same open file | Path unchanged | File identity can remain the same even though content and size change |
| Rename/move within the same filesystem | Path changes | Object is usually preserved, though provider semantics must be respected |
| Create an additional hard link under a new name | Two different paths | Can share the same file object and same key |
| Delete a file and create a new one at the same pathname | Same path as before | Usually a new object; freed IDs may be reused |
| Atomic replace of destination name with a new file | Destination name may stay the same | File object at target can change; older readers may still hold old handles depending on OS |
| Move across different filesystems via copy/delete | Path changes and file object can change | Key can change or cannot be directly compared across providers |

Therefore, do not permanently store `(path, fileKey)` as an "eternally unique immutable ID" for business data. If you need an ID that remains stable across machine moves, backups, restores, and file replacements, the application should generate its own **business identifier**.

### Does `fileKey` Help Detect File Replacement?

It can **assist** on some providers. For example, before reading a file, fetch the initial `fileKey`; after performing an operation, re-read and compare. If the key changed, that can signal the file object was replaced. However:

- If the key is `null`, this evidence is unavailable.
- A key can be reused after deletion/creation.
- The content of the same file can change without the key changing.
- Two attribute reads are not atomic with another process's operations.
- Comparing `key.equals(...)` alone while ignoring filesystem/provider is insufficient.

Consequently, this method suits certain limited checking/monitoring tasks, **not a locking/authorization mechanism** for dangerous operations. If you need to prevent target substitution between check and use, prefer handle/open-resource-based operations or appropriate protective filesystem APIs.

## 10. Size Changes and Non-Immutable Metadata

`BasicFileAttributes` is a result collected at **a single point in time**, not an object that automatically updates when the file changes. If you call `readAttributes()` before writing and keep `attrs`, `attrs.size()` still represents the collected value and does not grow automatically with the new file.

### Example 5 — comparing old and new attributes

```java
// FileSizeSnapshotDemo.java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public class FileSizeSnapshotDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("size-snapshot-", ".txt");

        try {
            Files.writeString(file, "A", StandardCharsets.UTF_8);
            BasicFileAttributes before = Files.readAttributes(
                    file, BasicFileAttributes.class);

            Files.writeString(file, "ABCDE", StandardCharsets.UTF_8);
            BasicFileAttributes after = Files.readAttributes(
                    file, BasicFileAttributes.class);

            System.out.println("oldSize=" + before.size());
            System.out.println("newSize=" + after.size());
            System.out.println("currentSize=" + Files.size(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac FileSizeSnapshotDemo.java
java FileSizeSnapshotDemo
```

Stdout when operating on the temporary regular file succeeds:

```text
oldSize=1
newSize=5
currentSize=5
```

`Files.writeString(file, text, UTF_8)` has no extra options, so for an existing file it writes data with default options including truncating prior content. `before` retains the old size. Discrepancies can appear when another program modifies the file, or when a buffered stream writer still holds unflushed data.

Important: even though reading `BasicFileAttributes` once can be more convenient than multiple separate attribute calls, it also **does not guarantee reading an immutable snapshot of the filesystem across the entire application lifecycle**.

## 11. Access Permissions and Exceptions When Reading Metadata

`Files.readAttributes()` can fail because the file no longer exists, access permissions are lacking, the mount/provider fails, or other conditions. A suitable handling pattern:

```java
// Illustrative code, path is a Path provided by the caller.
try {
    BasicFileAttributes attrs = Files.readAttributes(
            path, BasicFileAttributes.class);

    if (attrs.isRegularFile()) {
        System.out.println("Size in bytes: " + attrs.size());
    } else {
        System.out.println("Not a regular file");
    }
} catch (NoSuchFileException ex) {
    System.out.println("Path missing at metadata read time");
} catch (AccessDeniedException ex) {
    System.out.println("Cannot read attributes due to access restrictions");
} catch (IOException ex) {
    System.out.println("Other I/O failure: " + ex.getMessage());
}
```

The code above is **not standalone**; it requires appropriate imports and method scope. The illustrated subtypes represent common cases, though a provider may throw a general `IOException` for certain error types. If the application lacks permissions or the file is deleted after reading attributes, errors must still be handled **when actually opening/reading**.

`Files.exists(path)` or `Files.isRegularFile(path)` return useful booleans, yet might not fully distinguish "does not exist" from "cannot be determined". In particular, `Files.exists(path)==false` and `Files.notExists(path)==false` **can occur simultaneously** if the filesystem cannot determine the status. When you need the failure reason to show to users or retry, a `Files.readAttributes(...)` call with exceptions is usually better than relying solely on booleans.

### Permissions and File Type Are Not the Same Issue

A regular file can be **unreadable**; a symbolic link can lead to a restricted target; a directory can exist yet not be listable. Observing `isRegularFile()==true` does not mean `Files.newInputStream(path)` will definitely succeed.

In multi-user systems, metadata is a **filesystem fact**, not a business authorization policy. Do not use `fileKey` as a bearer token or proof of access permission; actual operations must go through proper authorization mechanisms.

## 12. Classifying File Counts in a Directory and the Role of `fileKey`

When computing size or gathering file statistics in a directory tree, `fileKey` can help avoid **double-counting the same object** on systems supporting hard links. However, you must distinguish two problem types:

- **Counting paths/entries**: one file with two hard links appears under two names, counting as two **entries**.
- **Counting distinct file objects**: two hard links can be treated as one object and one logical size, though handling must be consistent.
- **Allocated disk space**: summing logical `size()` does not answer this accurately because of sparse files, compression, metadata, and allocation policies.
- **Traversing symlinks**: if following symlinks, an object may be visited multiple times and symlink loops may occur.

Since `fileKey()` can be `null`, counting/deduplication algorithms need a **fallback**; do not simply insert `null` into a `Set` and conclude all key-less files are a single object. Alternatives depend on the goal: comparing identity with `Files.isSameFile()` (which has cost and exceptions), not following links, or simply counting entries instead of file objects.

In `Files.walkFileTree(...)`, choosing **whether to follow symbolic links** affects classification/traversal and cycle handling; do not use `fileKey` detached from the `FileVisitOption.FOLLOW_LINKS` contract and assume safety across all providers.

## 13. Choosing the Right Way to Fetch Metadata

| Problem | Suggested API | Notes |
| --- | --- | --- |
| Need only the size of a regular file | `Files.size(path)` | Bytes, can throw `IOException` |
| Need size + type + provider identity | `Files.readAttributes(path, BasicFileAttributes.class)` | Bundles info, `fileKey()` can be null |
| Need metadata **of the link** | `readAttributes(..., NOFOLLOW_LINKS)` | Differs from target metadata |
| Ask "is it a symbolic link?" | `Files.isSymbolicLink(path)` | Does not mean "target exists" |
| Ask "is it a regular file?" | `Files.isRegularFile(path, options...)` | Can return false when undetermined |
| Ask if two paths point to the same file? | `Files.isSameFile(pathA, pathB)` | Can throw `IOException`, and shortcuts when `Path.equals` |
| Ask what POSIX permissions a file has? | `Files.getPosixFilePermissions(...)` if supported | Distinct from `BasicFileAttributes`, provider-dependent |
| Ask about owner/ACL | `FileOwnerAttributeView`, `AclFileAttributeView` when supported | Not present by default on all filesystems |
| Want total size of a directory tree | Traverse tree, establish consistent summing rules | Do not use `size(directory)` |
| Want to detect content changes | Read data and hash or use a specific version mechanism | `fileKey` is not a content hash |
| Want to ensure opening a file with proper permissions | Perform the open operation per contract and catch exceptions | Do not rely solely on `isRegularFile()` assuming state won't change |

If advanced attributes beyond the basic group are needed, Java provides file-attribute views such as `PosixFileAttributes`, `DosFileAttributes`, and `AclFileAttributeView`. These APIs are **not guaranteed by every provider** and can throw `UnsupportedOperationException` when the feature is unavailable.

## 14. Common Mistakes

| Misconception / Error | Why It Is Wrong | How to Handle |
| --- | --- | --- |
| Thinking `size()` returns character count | Regular file size is in bytes | Distinguish UTF-8, UTF-16, and code points |
| Using `size(directory)` to compute directory size | Value for a directory is not consistently defined | Traverse the tree, explicitly define link/hard-link rules |
| Treating `File.length()==0` as definitely an empty file | A non-existent file can also return 0 | Check type, perform error-reporting queries |
| Treating `isRegularFile()==false` as meaning directory | Could be symlink, special file, or undetermined metadata | Check each type and handle errors |
| Using `isOther()` to check for missing files | `isOther()` describes object type, not absence | Catch `NoSuchFileException`/`IOException` |
| Reading a link without `NOFOLLOW_LINKS` and concluding it's a symlink | Default behavior may read target attributes | Specify `NOFOLLOW_LINKS` when querying the link |
| Assuming `fileKey()` is always available | It can return `null` | Design a fallback |
| Casting `fileKey()` to `long` and storing long-term as a global ID | Return type is `Object`, meaning is provider-specific, may be reused | Use within proper scope and maintain a dedicated business ID |
| Using `key.toString()` as a portable interchange format | Implementation varies by filesystem | Do not depend on key string format |
| Using `fileKey` to detect content changes | A file changing data can keep the same identity | Hash/version data as required |
| Equating `Path.equals()` with `Files.isSameFile()` | Path comparison differs from object check | Pick the API matching the question |
| Fetching attributes once and assuming they never change | File may be replaced or written afterward | Handle snapshots/races and actual operations |
| Summing every `attrs.size()` across hard links | May double-count the same file object | Decide whether to count entries or objects |
| Treating `Files.exists()==false` as certain file non-existence | Status is sometimes undetermined | Distinguish `notExists` and query exceptions |
| Trusting metadata checks to grant read permission | Metadata does not replace authorization | Open the file and handle permission/I/O errors |

## 15. Practice Exercises

### Exercise 1 — classification table

Write a program that creates an empty file and a temporary directory. Read `BasicFileAttributes` for each path and display `isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`. Explain why **the `isOther` flag does not represent a non-existent path**.

**Hint:** For a non-existent file, try `Files.readAttributes()` and catch `NoSuchFileException`; do not pretend you receive a valid attributes object.

### Exercise 2 — Unicode and byte counts

Write `"A😀"` as UTF-8, compare `Files.size()`, `attrs.size()`, `String.length()`, and `codePointCount(...)`. Then write different UTF-8 content to see the file size change according to the actual byte count.

**Hint:** The size of `"A😀"` when written in UTF-8 is **5 bytes**, not 2 or 3.

### Exercise 3 — hard links

If the filesystem supports it, create two hard-link paths to the same object. Compare `Path.equals`, `Files.isSameFile`, and `fileKey` (only when non-`null`). Why does only one of these checks definitively reflect **the identity question at query time**?

**Hint:** Two different names for the same object do not make two `Path`s structurally equal.

### Exercise 4 — symlinks

Create a symlink pointing to a regular file if permissions/provider allow. Compare `Files.readAttributes` when following links vs. not following links. Delete the target (keep the link), check `Files.exists` with and without `NOFOLLOW_LINKS`. Do not treat link size as target file size.

### Exercise 5 — statistics design

You are asked to "calculate the total size of files in a directory". Before writing the traversal loop, explain what must be clarified regarding: recursive vs. single level, following symbolic links, how many times hard links are counted, access permission errors, concurrently modified files, and logical bytes vs. allocated bytes.

## 16. Self-Check Questions

**1.** What unit do `Files.size(path)` and `BasicFileAttributes.size()` return for a regular file?

**Answer:** **Bytes**, type `long`, not UTF-16 `char`s or Unicode code points.

**2.** If `isRegularFile()==false`, is `isDirectory()==true` guaranteed?

**Answer:** No. There are other types such as symbolic links and other file types; you must also consider whether you are following links.

**3.** Is using `size(directory)` to find the total size of files inside accurate?

**Answer:** No. Directory size is not consistently defined and is not the sum of child file sizes.

**4.** Is `fileKey()` always a non-`null` integer?

**Answer:** No. The return type is `Object` and may be `null`; representation is decided by the provider.

**5.** If two paths have different `Path.toString()` values, can they point to the same file?

**Answer:** Yes. Hard links, symbolic links, or alternative naming can lead to the same physical file.

**6.** To query about **the symlink entry**, what option is passed when reading attributes?

**Answer:** `LinkOption.NOFOLLOW_LINKS` to `Files.readAttributes(...)`.

**7.** If a symbolic link has lost its target, are `Files.exists(link)` and `Files.exists(link, NOFOLLOW_LINKS)` necessarily equal?

**Answer:** No. Following the link can report the target does not exist; not following the link can confirm the link itself still exists.

**8.** A file's content is modified without replacing the object. Does `fileKey` necessarily change?

**Answer:** No. File identity and content are distinct.

**9.** Why should `fileKey` not be stored long-term as a global ID?

**Answer:** It is not guaranteed across all providers, not unique across filesystems, can be reused, and is not a stable business ID.

**10.** Does `Files.isSameFile(p, p)` returning `true` prove `p` exists?

**Answer:** Not necessarily. The API can return `true` immediately when two `Path`s are equal without querying the filesystem.

**11.** After calling `Files.readAttributes`, can another process delete/replace the file before you open it?

**Answer:** Yes. Metadata is information at query time and does not eliminate races. You must handle errors on the actual operation.

**12.** When counting files in a tree containing hard links and symlinks, why must the policy be agreed upon upfront?

**Answer:** One object can appear via multiple paths. Counting entries, logical file objects, and allocated disk usage are calculations with different meanings.

**Summary:** With Java NIO.2, `BasicFileAttributes` helps fetch **byte size**, **file object type**, and provider-supplied **`fileKey`**. Pay attention to `NOFOLLOW_LINKS` when querying a symbolic link instead of its target; do not use directory size to infer total space; do not treat `fileKey` as a global ID or content hash. Use `Files.isSameFile()` when checking current identity and handle `IOException`/TOCTOU in every real operation.
