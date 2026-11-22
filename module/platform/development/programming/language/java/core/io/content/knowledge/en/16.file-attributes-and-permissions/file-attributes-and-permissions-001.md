# BasicFileAttributes and BasicFileAttributeView in Java NIO

In Java NIO.2, **`java.nio.file.attribute.BasicFileAttributes`** and **`java.nio.file.attribute.BasicFileAttributeView`** both relate to the metadata of a file or directory, but **do not share the same role**:

- **`BasicFileAttributes`** is a **read-only data interface**: it holds fetched values such as entry type, size, timestamps, and a file identifier key if available.
- **`BasicFileAttributeView`** is an **interface for accessing the basic attribute group of a path**: it allows calling `readAttributes()` to read a fresh attribute set and `setTimes(...)` to request changing certain timestamps.

Reading attributes is not equivalent to opening file contents. Updating timestamps is not updating byte contents. In addition, file system metadata can change immediately after being read, depending on permissions, file type, symbolic links, and file system provider capabilities.

## 1. Learning Objectives

After this lesson, you can:

1. Name and properly use the methods of `BasicFileAttributes`: `size`, `creationTime`, `lastModifiedTime`, `lastAccessTime`, `isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`, `fileKey`.
2. Read metadata in a type-safe manner using `Files.readAttributes(path, BasicFileAttributes.class)`.
3. Obtain a `BasicFileAttributeView` from `Files.getFileAttributeView(...)` and use `view.readAttributes()` or `view.setTimes(...)`.
4. Understand `null` parameters of `setTimes`, timestamp precision, I/O errors, and provider-dependent behaviors.
5. Distinguish a metadata snapshot from the actual file, without inferring that reading attributes is an atomic lock/snapshot operation across the entire system.
6. Distinguish the default symbolic-link-following mode from `LinkOption.NOFOLLOW_LINKS`.
7. Recognize when specialized views such as `PosixFileAttributeView` or `DosFileAttributeView` are needed instead of trying to use the basic view to change permissions.
8. Write a compilable/runnable Java 17+ program that inspects metadata on temporary files and handles the case where a file does not exist yet.

## 2. Two Abstractions: Value Set and Operation Window

Visualize the relationship:

~~~text
Path
  |
  +-- Files.readAttributes(path, BasicFileAttributes.class)
  |          |
  |          v
  |    BasicFileAttributes
  |      size, timestamps, type, fileKey...
  |      (newly read data, no setters)
  |
  +-- Files.getFileAttributeView(
         path, BasicFileAttributeView.class
      )
             |
             v
       BasicFileAttributeView
         + readAttributes()
         |      |
         |      v
         |  New BasicFileAttributes
         |
         + setTimes(modified, accessed, created)
                |
                v
          Request file system update
~~~

`BasicFileAttributes` returns the result observed in **a single read**. If more bytes are written to the file one minute later, the attributes object you are holding does not automatically refresh `size()` or `lastModifiedTime()`; you must request a re-read.

`BasicFileAttributeView` represents the API of **an attribute group** bound to a `Path`. A view is not a file handle that permanently locks an entry. You can obtain a view first, and by the time you call `readAttributes`, the path may have changed or no longer exist, causing the operation to fail. You should distinguish **obtaining a view** from **reading attributes at the time of use**.

Main types:

~~~java
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.BasicFileAttributeView;

Path path = Path.of("data.txt");

BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

BasicFileAttributeView view =
        Files.getFileAttributeView(
                path, BasicFileAttributeView.class);

BasicFileAttributes refreshed = view.readAttributes();
~~~

This is a **code snippet**; it must be placed inside a method that declares or handles `IOException`, and `data.txt` must exist/be accessible for the reads to succeed. `getFileAttributeView` may return `null` if the provider does not support the requested view type; when writing general-purpose APIs, check for `null` before using it.

## 3. What Does `BasicFileAttributes` Provide?

This is an interface in the `java.nio.file.attribute` package. It declares the following methods:

| Method | Return Type | Meaning |
| --- | --- | --- |
| `lastModifiedTime()` | `FileTime` | Last modification time reported by the file system |
| `lastAccessTime()` | `FileTime` | Last access time reported by the file system |
| `creationTime()` | `FileTime` | Creation time reported by the file system |
| `size()` | `long` | Reported size, typically in **bytes** for regular files |
| `isRegularFile()` | `boolean` | Whether it is a regular file |
| `isDirectory()` | `boolean` | Whether it is a directory |
| `isSymbolicLink()` | `boolean` | Whether it is a symbolic link |
| `isOther()` | `boolean` | Whether it is another entry type besides the three above |
| `fileKey()` | `Object` or `null` | File identifier key if provided by the provider |

### FileTime and Timestamps

`FileTime` represents a point in time and can be converted to an `Instant` or other appropriate time units.

~~~java
FileTime modified = attrs.lastModifiedTime();
System.out.println(modified.toInstant());
~~~

This is a snippet using `attrs` already read from a file. Do not print a fixed timestamp in exercises unless you explicitly set the value and verified that the provider supports that precision.

The three timestamps are commonly understood as:

- **last modified**: last modification of content/metadata as defined by the system, usually related to file content changes.
- **last accessed**: last access time; many file systems/mounts do not update access time on every read for performance reasons.
- **creation**: creation time; some systems do not store this timestamp as an independent field.

**Important Java contract:** if the system does not support a timestamp, the method may still return an **implementation-specific default value**, such as the last modified time or the epoch, instead of reporting "unavailable" with `null`. Do not assume every `creationTime()` definitely reflects the true birth time of the file.

### `size()` Measures Bytes, Not Java Characters

For regular files, `size()` returns the size in bytes reported by the file system, **not**:

- `String.length()` (UTF-16 `char` units),
- number of visible characters,
- number of lines,
- number of Unicode code points.

For example, the string `"Xin chào"` written in UTF-8 can have more bytes than visible characters. For compressed or sparse files, the reported byte count might not match the actual physical storage occupied. For directories or non-regular entries, the size value is **implementation-dependent** and does not mean "total size of all child files".

### Four File Type Classification Predicates

~~~java
if (attrs.isRegularFile()) {
    // Regular file, with byte-based content.
} else if (attrs.isDirectory()) {
    // Directory.
} else if (attrs.isSymbolicLink()) {
    // The symbolic link itself if read with NOFOLLOW_LINKS.
} else if (attrs.isOther()) {
    // Other type, e.g., a special object defined by the provider.
}
~~~

The snippet above uses an already declared `attrs`. The classification information is determined **at the time of reading**, and does not grant access permission or lock the file. When reading attributes with default behavior (following links), `isSymbolicLink()` can be false even if the input path is a symbolic link, because you are inspecting the attributes of **the link's target**.

### `fileKey()` Is an Identifier Key, Not a Path

`fileKey()` may return an object used to identify a file within the scope of a provider, such as a device ID/inode combination on some Unix systems. However:

- Providers are allowed to return `null` when no file key is available.
- Do not treat `fileKey().toString()` as a standard format or a stable ID for long-term storage.
- Uniqueness is only guaranteed while the file system and file remain intact; after deletion, IDs may be reused.
- Do not arbitrarily compare file keys from two different providers.
- If you need to determine **whether two `Path`s point to the same file**, use `Files.isSameFile(path1, path2)` according to its own contract, while still accounting for the possibility that the file changes immediately afterward.

## 4. Complete Java 17+ Program: Reading Regular File Attributes

Create the file **`BasicAttributesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.BasicFileAttributeView;

public class BasicAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("basic-attrs-");
        Path file = directory.resolve("hello.txt");

        try {
            Files.writeString(file, "Hello!", StandardCharsets.UTF_8);

            BasicFileAttributes attrs =
                    Files.readAttributes(
                            file, BasicFileAttributes.class);

            BasicFileAttributeView view =
                    Files.getFileAttributeView(
                            file, BasicFileAttributeView.class);

            if (view == null) {
                throw new IOException("Basic attribute view unavailable");
            }

            BasicFileAttributes viaView = view.readAttributes();

            System.out.println("view=" + view.name());
            System.out.println("regular=" + attrs.isRegularFile());
            System.out.println("directory=" + attrs.isDirectory());
            System.out.println("symbolicLink=" + attrs.isSymbolicLink());
            System.out.println("other=" + attrs.isOther());
            System.out.println("bytes=" + attrs.size());
            System.out.println("viaViewBytes=" + viaView.size());
            System.out.println("hasModifiedTime=" +
                    (attrs.lastModifiedTime() != null));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run:

~~~bash
javac BasicAttributesDemo.java
java BasicAttributesDemo
~~~

**Expected stdout on a typical default file system without concurrent file edits:**

~~~text
view=basic
regular=true
directory=false
symbolicLink=false
other=false
bytes=6
viaViewBytes=6
hasModifiedTime=true
~~~

Explanation:

1. `Files.createTempDirectory` creates a real directory. The path to `hello.txt` initially has no target file.
2. `Files.writeString` writes the 6 ASCII bytes of `Hello!` in UTF-8.
3. `Files.readAttributes` retrieves an attribute set typed as `BasicFileAttributes`.
4. `Files.getFileAttributeView` returns the view named `"basic"`; `view.readAttributes()` reads a corresponding metadata set in **another call**.
5. `size() == 6` holds because the string `Hello!` consists of six UTF-8 bytes.
6. Specific timestamp values are not printed because they are unstable across environments and execution times.
7. `finally` cleans up temporary resources. If cleanup fails, an `IOException` can still propagate.

**Do not infer that the two objects `attrs` and `viaView` are the same instance or part of a shared atomic snapshot.** They are obtained via two separate read calls; their contents can differ if another actor modifies the file in between.

## 5. `BasicFileAttributeView`: Window to Read and Update Timestamps

This interface extends `FileAttributeView` and provides three main capabilities:

~~~java
String name();
BasicFileAttributes readAttributes() throws IOException;
void setTimes(
        FileTime lastModifiedTime,
        FileTime lastAccessTime,
        FileTime createTime
) throws IOException;
~~~

The view's name is **`"basic"`**. `readAttributes()` retrieves basic attributes as a **bulk operation** (a single API call). However, the documentation **does not guarantee that all attributes are read atomically relative to other file system operations**; that is implementation-dependent.

`setTimes(...)` requests changing one or more timestamps. It is **not** used to update size, file key, file type, name, ACLs, or permissions. Those parts are either read-only information or require other APIs.

### Syntax and `null` Parameter Rules

~~~java
view.setTimes(modifiedTime, null, null);
~~~

This means requesting to update only **last modified time**, while last access and creation time are passed `null` and therefore **not requested to change**.

~~~java
view.setTimes(null, accessedTime, null);
~~~

Requests changing only last access time.

~~~java
view.setTimes(null, null, createdTime);
~~~

Requests changing only creation time, **if supported by the provider/file store**.

~~~java
view.setTimes(null, null, null);
~~~

Changes no timestamps according to the contract.

**Caution:** `null` here means "do not change the corresponding attribute", **not** "set the time to null/1970". Java may need to read the existing values when changing only some fields and then write them back; therefore updates are not guaranteed to be atomic and can sometimes lose precision on other timestamps.

### Precision and Unsupported Values

`FileTime` can represent a very precise instant, but a file store might only store timestamps at second, millisecond, or another resolution. When updating:

- Java converts the value to the unit/precision supported by the file store.
- Converting from higher precision to lower precision may round or truncate fractional parts.
- For unsupported or out-of-range timestamps, the behavior is **not completely specified**: the operation may or may not throw an `IOException`.
- Therefore, **read back to verify** if the timestamp is a critical business requirement; do not assume a normal return from `setTimes` always produces exact nanosecond accuracy.

## 6. Complete Java 17+ Program: Updating Modification Time

Create the file **`BasicTimesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.time.Instant;

public class BasicTimesDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("basic-times-");
        Path file = folder.resolve("data.txt");

        try {
            Files.writeString(file, "data", StandardCharsets.UTF_8);

            BasicFileAttributeView view =
                    Files.getFileAttributeView(
                            file, BasicFileAttributeView.class);
            if (view == null) {
                throw new IOException("Basic view unavailable");
            }

            FileTime requested =
                    FileTime.from(Instant.parse("2020-01-02T03:04:05Z"));

            // Update only last-modified-time.
            view.setTimes(requested, null, null);

            BasicFileAttributes after = view.readAttributes();

            System.out.println("view=" + view.name());
            System.out.println("regular=" + after.isRegularFile());
            System.out.println("requestedYear="
                    + requested.toInstant().atZone(
                            java.time.ZoneOffset.UTC).getYear());
            System.out.println("actualTimestamp="
                    + after.lastModifiedTime());
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Compile and run:

~~~bash
javac BasicTimesDemo.java
java BasicTimesDemo
~~~

**Example stdout on a file store supporting the requested time:**

~~~text
view=basic
regular=true
requestedYear=2020
actualTimestamp=2020-01-02T03:04:05Z
~~~

The line `actualTimestamp` is **not a guaranteed result across all platforms**: a provider may change precision, reject the update, or report an implementation-specific timestamp. That is why the program reads the attributes back after `setTimes`, rather than printing the requested value as proof of success.

If the application needs second-level precision, compare according to application policy after readback:

~~~java
boolean sameSecond =
        after.lastModifiedTime().toInstant().getEpochSecond()
        == requested.toInstant().getEpochSecond();
~~~

This is a snippet using `after` and `requested` from the example above. It compares to the **second**, without requiring identical nanoseconds, yet can still return `false` if the file store cannot store the value or the operation did not actually achieve the desired update. Do not ignore `false` when the timestamp is a business constraint.

## 7. Read Once with `Files.readAttributes` or Hold `BasicFileAttributeView`?

There are two common approaches.

### Approach A — Direct Read

~~~java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);
~~~

Advantages:

- Concise and statically typed.
- Suitable when you only need to **read a metadata snapshot**.
- All fields can be accessed multiple times from the result object without re-reading the file system.
- Can pass `LinkOption.NOFOLLOW_LINKS` to read the symbolic link itself.

### Approach B — Obtain a View and Operate

~~~java
BasicFileAttributeView view =
        Files.getFileAttributeView(
                path, BasicFileAttributeView.class);

BasicFileAttributes before = view.readAttributes();
view.setTimes(newTime, null, null);
BasicFileAttributes after = view.readAttributes();
~~~

This is a code snippet; `path` has type `Path`, `newTime` has type `FileTime`, and `IOException` must be handled. If the view might be `null`, check it before calling its methods.

Advantages:

- Groups reading and requesting timestamp updates through **the same attribute view type**.
- Convenient when you need to read–modify–re-read multiple times within one method.
- Allows APIs to work with different attribute views when designing extensible systems.

Both operate on the file system at call time; **a view does not guarantee the path still exists, holds no lock, and does not automatically synchronize with other writers**.

| Need | Recommendation |
| --- | --- |
| Quickly inspect size, type, modification time | `Files.readAttributes(path, BasicFileAttributes.class)` |
| Read attributes with symlink control | `Files.readAttributes(path, BasicFileAttributes.class, NOFOLLOW_LINKS)` |
| Read and update timestamps through the same abstraction | `Files.getFileAttributeView(...).setTimes(...)` then `readAttributes()` |
| Need only last-modified-time | `Files.getLastModifiedTime` / `Files.setLastModifiedTime` |
| Read attributes by dynamic string name | `Files.getAttribute` / `Files.readAttributes(path, "basic:*")` |
| Modify POSIX permissions or ACLs | Use the corresponding specialized attribute views/APIs, not the basic view |

## 8. Typed Attributes vs. Attribute-Name Strings

Java also provides dynamic attribute APIs based on string names, for example:

~~~java
Map<String, Object> values =
        Files.readAttributes(path, "basic:*");
~~~

It returns a `Map<String, Object>` instead of a `BasicFileAttributes` with compile-time type-checked methods.

The names in the `basic` group include:

- `lastModifiedTime` — `FileTime`
- `lastAccessTime` — `FileTime`
- `creationTime` — `FileTime`
- `size` — `Long`
- `isRegularFile` — `Boolean`
- `isDirectory` — `Boolean`
- `isSymbolicLink` — `Boolean`
- `isOther` — `Boolean`
- `fileKey` — `Object` (may be `null`)

When you want a single attribute:

~~~java
FileTime modified =
        (FileTime) Files.getAttribute(
                path, "basic:lastModifiedTime");
~~~

When you want to request a change:

~~~java
Files.setAttribute(
        path,
        "basic:lastModifiedTime",
        requestedTime
);
~~~

These are **code snippets** requiring imports for `java.nio.file.Files`, `Path`, `Map`, `FileTime`, declarations for variables `path`/`requestedTime`, and `IOException` handling.

**Important:** do not infer that every key in `basic:*` can be passed to `setAttribute`. The basic view only provides setter behavior for the **three time fields** per `setTimes`. Attributes such as `size`, `isRegularFile`, and `fileKey` have no corresponding setters in `BasicFileAttributeView`.

For application code that knows the required fields statically, the typed version is usually easier to maintain because it avoids manual `Object` casts and attribute-name typos.

## 9. Symbolic Links and `LinkOption.NOFOLLOW_LINKS`

This is one of the most important reasons to understand **whose attributes are being read**.

Suppose:

~~~text
data.txt                 (regular file)
shortcut -> data.txt     (symbolic link)
~~~

When reading with default behavior:

~~~java
BasicFileAttributes followed =
        Files.readAttributes(
                shortcut, BasicFileAttributes.class);
~~~

`Files.readAttributes` **follows symbolic links** by default. If the target exists and is a regular file, `followed.isRegularFile()` is typically `true`; `followed.isSymbolicLink()` is typically `false` because the attributes describe **the target after following the link**.

To read **the link entry itself**:

~~~java
BasicFileAttributes linkAttrs =
        Files.readAttributes(
                shortcut,
                BasicFileAttributes.class,
                LinkOption.NOFOLLOW_LINKS);

System.out.println(linkAttrs.isSymbolicLink());
~~~

This is a snippet requiring `shortcut` of type `Path`, appropriate imports, and `IOException` handling. If the link actually exists, the attributes of the link itself have `isSymbolicLink() == true`.

Similarly with an attribute view:

~~~java
BasicFileAttributeView linkView =
        Files.getFileAttributeView(
                shortcut,
                BasicFileAttributeView.class,
                LinkOption.NOFOLLOW_LINKS
        );
~~~

`linkView.readAttributes()` targets the link itself according to the view's policy. `setTimes` when using this view may also relate to updating the timestamps of **the link entry**, and support for operations on links depends on the file system/provider.

**Do not assume symlink creation code works by default in all CI tests:** on some operating systems, user privileges and providers may disallow creating symlinks. When real tests are needed, set up fixtures based on environment capabilities or skip when unsupported.

### Dangling Symbolic Links

If `shortcut` points to a non-existent target:

- Reading attributes **following links** can fail with `NoSuchFileException`.
- Reading attributes with `NOFOLLOW_LINKS` can still describe **the link itself** if the link entry exists.

Therefore, `Files.exists(shortcut)==false` by default does not by itself prove that no link entry exists at that path. If you need to inspect the link entry, choose `NOFOLLOW_LINKS` and handle unknown/access-denied conditions.

## 10. Non-Existent Files and Views Created Before the File Appears

`Path` represents a location, not an opened file; obtaining an attribute view should likewise not be mistaken for having read real metadata.

Create the file **`MissingAttributesDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributeView;

public class MissingAttributesDemo {
    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("missing-attrs-");
        Path missing = folder.resolve("absent.txt");

        try {
            BasicFileAttributeView view =
                    Files.getFileAttributeView(
                            missing, BasicFileAttributeView.class);

            System.out.println("viewAvailable=" + (view != null));

            if (view == null) {
                return;
            }

            try {
                view.readAttributes();
                System.out.println("unexpected success");
            } catch (NoSuchFileException exception) {
                System.out.println("read=NoSuchFileException");
            }
        } finally {
            Files.deleteIfExists(folder);
        }
    }
}
~~~

Compile and run:

~~~bash
javac MissingAttributesDemo.java
java MissingAttributesDemo
~~~

**Expected stdout on a typical default file system:**

~~~text
viewAvailable=true
read=NoSuchFileException
~~~

Lessons:

1. `getFileAttributeView` can return a view for **a `Path` that does not exist yet**.
2. `view != null` only proves that the view type is supported by the provider; **it does not prove the file currently exists or is readable**.
3. Only `readAttributes()` attempts to fetch real metadata, so a missing path usually leads to `NoSuchFileException`.
4. Do not use a view as a replacement for `Files.exists`; even if a prior check succeeds, the file can still change immediately afterward.

With special file system providers, the specific exception type may differ; the example uses `NoSuchFileException` to illustrate the default provider, while production code must still handle `IOException`.

## 11. Is Metadata an "Atomic Snapshot" of a File?

**Do not assume so by default.**

`BasicFileAttributeView.readAttributes()` reads the attribute set as a bulk operation. However, according to the Java documentation, **whether all fields are read atomically with respect to other file system operations is implementation-specific**.

A timeline might look like this:

~~~text
Thread A                         Thread B
--------                         --------
readAttributes() starts
                                 writes more data to the file
reads attrs.size()
                                 updates metadata timestamp
receives attrs
...
uses stale result
~~~

Program A may see metadata from one moment, and by the time it opens the file to read content, the size/content has changed. An already received `BasicFileAttributes` keeps its old values and does not track the file in real time.

Example scenario:

~~~java
BasicFileAttributes before =
        Files.readAttributes(path, BasicFileAttributes.class);

// Another user/another process might modify the file here.

byte[] bytes = Files.readAllBytes(path);
boolean sizeMatched = before.size() == bytes.length;
~~~

This is a snippet placed in a method handling `IOException` with a declared `path` variable. `sizeMatched` can be false due to file changes, and even if true, **it does not guarantee the bytes belong to the same content version** (the file could be edited without changing its size).

If you need a truly consistent snapshot, rely on a system mechanism: immutable/versioned files, file locks where supported, copying to staging, transactional storage, or a coordination protocol between writers and readers. A `BasicFileAttributes` object does not create that guarantee by itself.

## 12. `setTimes` Is Not an Atomic Transaction and Does Not Change Permissions

A statement like:

~~~java
view.setTimes(newModified, null, null);
~~~

may need to read existing timestamps and then write new metadata, depending on the provider. It does not promise:

- Atomically updating all three timestamps simultaneously.
- Preserving the precision of other timestamps across all file stores.
- Preventing another actor from modifying the file right after setting.
- Keeping a fixed file identity under the same `Path`.
- Changing `size`, `fileKey`, owner, ACL, or POSIX permissions.

If you need to change permissions, use the appropriate APIs, for example:

~~~java
// API illustration only; does not run on every file system.
Files.setPosixFilePermissions(path, permissions);
~~~

This is a snippet with `permissions` of type `Set<PosixFilePermission>`, depending on provider support and execution privileges. It is not a method of `BasicFileAttributeView`.

For Windows/DOS-style attributes such as `hidden`, `readOnly`, `system`, `archive`, look at `DosFileAttributeView`. For POSIX owner/group/permissions, look at `PosixFileAttributeView`. Specialized views may not be supported on a provider, so `getFileAttributeView` may return `null` or the corresponding API may throw an error.

## 13. Distinguishing Basic, DOS, and POSIX

| View | Primary Attribute Group | Additional Behavior |
| --- | --- | --- |
| `BasicFileAttributeView` | Type, size, timestamps, fileKey | `readAttributes`, `setTimes` |
| `DosFileAttributeView` | Basic + hidden, read-only, archive, system | Has corresponding setters when supported |
| `PosixFileAttributeView` | Basic + POSIX owner, group, permission bits | Has APIs to change owner/group/permissions when supported |
| `AclFileAttributeView` | ACLs per provider's supported model | Read/write ACLs when supported |
| `UserDefinedFileAttributeView` | User-defined extended attributes | Read/write specific names/values when supported |

Not every file system provides every view type. Do not use `BasicFileAttributes` to conclude whether a file "is readable": it **does not define a `canRead()` method**. To assess accessibility, use corresponding APIs like `Files.isReadable` (which only checks at a point in time), or perform the actual open/read operation and handle real errors.

When writing cross-platform code:

~~~java
if (Files.getFileAttributeView(
        path, java.nio.file.attribute.PosixFileAttributeView.class) != null) {
    // The provider supplies a POSIX attribute view.
}
~~~

This is a code snippet; it does not guarantee permission-changing operations will succeed — that still depends on actual file permissions and the file still existing at the time of the operation.

## 14. I/O Errors and Exceptions to Handle

Attribute reading operations can fail because:

- The file or directory has been deleted or never existed.
- A symbolic link is broken or cannot be resolved when following links.
- Permission to read metadata is denied.
- The file system provider or network device encounters an error.
- The file is replaced during the query.
- The provider does not support the requested view or attribute.
- The new timestamp is outside the supported range or precision.

Example of explicit error-handling code:

~~~java
import java.io.IOException;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;

public final class AttributeReader {
    private AttributeReader() {}

    public static BasicFileAttributes requireMetadata(Path path)
            throws IOException {
        try {
            return Files.readAttributes(
                    path, BasicFileAttributes.class);
        } catch (NoSuchFileException exception) {
            throw new IOException("File not found: " + path,
                    exception);
        } catch (AccessDeniedException exception) {
            throw new IOException("Cannot inspect metadata: " + path,
                    exception);
        }
    }
}
~~~

This is a **compilable utility class** (without `main`). It preserves the underlying cause inside `IOException(message, cause)` so callers/logs have additional context. Providers are not required to always use the exact same specific subclass in every situation, so other `IOException`s are still propagated.

With dynamic map-reading APIs, unsupported attribute names can throw `IllegalArgumentException` or `UnsupportedOperationException` according to each method's contract. Do not catch all `RuntimeException`s and lump them into "file does not exist".

Certain `false` results from `Files.isRegularFile(path)` / `Files.exists(path)` can mean the status could not be determined; when business logic needs the reason, `Files.readAttributes` provides a clearer error reporting path.

### Security and Access Control

Metadata can contain sensitive paths, file IDs, or timestamps in certain contexts. Do not habitually log user info or absolute paths to public logs. If paths come from untrusted sources, enforce controls against path traversal/symlinks and actual operation permissions. A successful `readAttributes()` call neither grants file access permission nor protects against TOCTOU.

## 15. When to Use `Files.size` / `getLastModifiedTime` Instead of Reading Multiple Fields

If you only need **one field**, utility APIs can be clearer:

~~~java
long bytes = Files.size(path);
FileTime modified = Files.getLastModifiedTime(path);
~~~

If you need **multiple fields** to display or classify a file:

~~~java
BasicFileAttributes attrs =
        Files.readAttributes(
                path, BasicFileAttributes.class);

long bytes = attrs.size();
boolean directory = attrs.isDirectory();
FileTime modified = attrs.lastModifiedTime();
~~~

The first calls are two separate queries; the latter retrieves the attribute set in one call. You should not claim that reading once guarantees all fields are atomic, yet when the goal is to read multiple attributes close together in time, a typed attribute set is a convenient solution and can reduce metadata round trips.

If you need to change timestamps, use `Files.setLastModifiedTime` for simple cases; use `BasicFileAttributeView.setTimes` when you want to change other timestamps or multiple timestamps through the same API.

**Do not misuse `Files.size` to reliably predict the exact byte count you will receive on the next read**: the file may change. When reading in a streaming manner, the actual bytes read and EOF from the stream remain the ground truth to handle.

## 16. Practical Application: File Statistics and Type Filtering

Example application listing a directory and processing only regular files, with metadata fetched from each path:

~~~java
try (java.nio.file.DirectoryStream<Path> stream =
             Files.newDirectoryStream(directory)) {
    for (Path child : stream) {
        BasicFileAttributes attrs =
                Files.readAttributes(
                        child, BasicFileAttributes.class,
                        java.nio.file.LinkOption.NOFOLLOW_LINKS);
        if (attrs.isRegularFile()) {
            System.out.println(child.getFileName() + ": "
                    + attrs.size() + " bytes");
        }
    }
}
~~~

This is a **code snippet** inside a method with appropriate variables/imports and `IOException` handling (errors occurring while iterating `DirectoryStream` may be wrapped in `DirectoryIteratorException`). `DirectoryStream` is a resource that must be closed. Reading with `NOFOLLOW_LINKS` means a symlink to a file will **not** be considered a regular file in that classification pass.

If you need to scan a large directory tree, you can use `Files.walkFileTree` and leverage the `BasicFileAttributes` supplied in the `FileVisitor` callback. You do not necessarily have to query metadata a second time if the callback already provides the suitable attribute set.

### Callback in `walkFileTree`

~~~java
@Override
public FileVisitResult visitFile(
        Path file, BasicFileAttributes attrs) throws IOException {
    if (attrs.isRegularFile()) {
        totalBytes += attrs.size();
    }
    return FileVisitResult.CONTINUE;
}
~~~

This is a **code snippet of a class extending `SimpleFileVisitor<Path>`** with a `totalBytes` field declared in the class and imports for `FileVisitResult`, `Path`, `BasicFileAttributes`, `IOException`. The callback receives an attribute snapshot per the traversal process. If a file changes between traversal and processing, `attrs.size()` does not necessarily match the number of bytes later read.

## 17. Common Misconceptions

**1. "`BasicFileAttributes` is a live object; when the file changes, `attrs.size()` changes."**  
False. `attrs` is data read at a point in time; to get updates, you must re-read the metadata.

**2. "`BasicFileAttributeView` is itself the list of attributes."**  
False. A view is an API to read and update; `view.readAttributes()` is what returns the `BasicFileAttributes` data set.

**3. "`getFileAttributeView(...) != null` proves the file currently exists."**  
False. It primarily proves the provider supports that view type; `readAttributes()` is what actually accesses metadata and can fail.

**4. "`setTimes(null, null, null)` sets timestamps to the epoch."**  
False. All three `null`s mean changing no fields; an individual `null` keeps the corresponding timestamp unchanged.

**5. "`setTimes` guarantees changing all three times simultaneously and atomically."**  
False. File system providers may perform intermediate reads/writes and lose precision, especially when changing only some fields.

**6. "`creationTime()` is always the actual creation date."**  
False. If the file system does not support creation time, the result may be an implementation-specific value such as the last modified time or epoch.

**7. "`attrs.size()` reports the size of an entire directory."**  
False. The size of a non-regular file entry is not universally specified that way.

**8. "`fileKey()` is always non-null and can be stored as a permanent ID."**  
False. It can be null; it is not guaranteed to remain stable after the file is deleted/replaced or moved to another file system.

**9. "Reading attributes from a symlink always reports `isSymbolicLink()==true`."**  
False. By default `Files.readAttributes` follows symlinks; to read the link itself, use `NOFOLLOW_LINKS`.

**10. "The basic view allows changing owner, permissions, and ACLs."**  
False. The basic view only defines `setTimes` for timestamps; specialized views are required when updating permissions or security attributes.

**11. "Successfully reading metadata implies subsequent file opens or writes will succeed."**  
False. Permissions, file identity, and state can change; you must handle I/O errors at the actual operation.

**12. "All providers throw the exact same `IOException` subclass."**  
False. Java allows differences in specific exception types and attribute view capabilities; code must be ready to handle `IOException`.

## 18. Project Adoption Checklist

- [ ] Have you distinguished the `BasicFileAttributes` data object from the `BasicFileAttributeView` view?
- [ ] Did you choose `Files.readAttributes(..., BasicFileAttributes.class)` when reading multiple typed attributes?
- [ ] Do you re-read when updated information is needed, rather than keeping one `attrs` object forever?
- [ ] Do you understand `size` is a byte count, not character count or recursive directory size?
- [ ] Have you verified the meaning of `creationTime/lastAccessTime` on the actual file system instead of trusting them blindly?
- [ ] If symlink metadata is needed, did you use `NOFOLLOW_LINKS` appropriately?
- [ ] Did you check view support and handle missing paths, I/O errors, or insufficient permissions?
- [ ] When calling `setTimes`, did you pass `null` for timestamps you do not want to change?
- [ ] When timestamps are a business constraint, did you read back and evaluate precision?
- [ ] Did you avoid using `fileKey` as a permanent ID or concluding identity when files may change?
- [ ] Did you use POSIX/DOS/ACL views appropriately if permissions/attributes beyond basic are needed?
- [ ] Did you handle TOCTOU if files may be modified by other actors?
- [ ] When iterating many entries, did you close `DirectoryStream`/`Stream<Path>` and handle iteration errors?
- [ ] Did you test results on the actual target file systems/providers?

## 19. Self-Check Questions

**Question 1.** What is the difference between `BasicFileAttributes` and `BasicFileAttributeView`?  
**Answer:** `BasicFileAttributes` is a read metadata value set; `BasicFileAttributeView` is an API to call re-reads and request timestamp updates.

**Question 2.** To find size, file type, and timestamps with a single typed query, what do you use?  
**Answer:** `Files.readAttributes(path, BasicFileAttributes.class)`.

**Question 3.** Which field does `view.setTimes(null, accessTime, null)` change?  
**Answer:** It only requests changing last-access-time; the other two fields are kept unchanged per the contract.

**Question 4.** For a `Path` without an existing file, can `getFileAttributeView` return a view?  
**Answer:** Yes. Obtaining a view does not prove the file exists; `view.readAttributes()` may throw `NoSuchFileException`.

**Question 5.** Does `attrs.fileKey() == null` mean the file is corrupted?  
**Answer:** No. The provider may simply not supply a file key.

**Question 6.** Does `attrs.size()` for a directory always equal the sum of bytes of child files?  
**Answer:** No. The size of a non-regular file entry is implementation-dependent.

**Question 7.** To inspect metadata of the symbolic link itself rather than the target, what is needed?  
**Answer:** Read with `LinkOption.NOFOLLOW_LINKS`.

**Question 8.** If `setTimes` completes and reading back does not match to the exact nanosecond, is Java definitely buggy?  
**Answer:** No. The file store may have lower resolution, or a timestamp may be unsupported. You must evaluate according to application/file system policy.

**Question 9.** Can you use the basic view to modify POSIX permissions?  
**Answer:** No. Use the POSIX attribute APIs if the provider supports them.

**Question 10.** Does `readAttributes` guarantee an atomic snapshot when the file is modified concurrently?  
**Answer:** No. Java explicitly states that atomicity of bulk metadata reads is implementation-dependent.

**Key Takeaway:** **`BasicFileAttributes` tells you what was just observed; `BasicFileAttributeView` gives you a way to read/propose updates to those attributes**. In particular, `readAttributes()` does not lock the file and `setTimes()` promises neither atomicity nor absolute precision. Pay attention to symbolic links, permissions, providers, and handle `IOException` on every actual operation.

## Java SE 17 Documentation

- [BasicFileAttributes — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
- [BasicFileAttributeView — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributeView.html)
- [Files.readAttributes / getFileAttributeView — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [FileTime — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html)
- [LinkOption — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html)
