# Reading Attributes by Type or by Name in Java NIO.2

When working with files and directories, in addition to reading contents, applications often need to know **size (bytes), modification time, resource type, owner, or access permissions**. Java NIO.2, through `java.nio.file.Files` and `java.nio.file.attribute`, provides two primary ways to read **multiple attributes of a `Path`**:

1. **By type (typed):** `Files.readAttributes(path, BasicFileAttributes.class)` returns an object implementing a compile-time interface.
2. **By name (named):** `Files.readAttributes(path, "basic:size,lastModifiedTime")` returns a `Map<String,Object>` containing the attributes requested by string names.

If you only need **one** attribute, there is `Files.getAttribute(path, "basic:size")`. Each approach has different advantages regarding clarity, extensibility, and provider requirements.

This lesson is part of the **Attributes and Permissions** section of Java Core I/O, using Java 17+. The focus is on reading metadata **without modifying data**, properly understanding `basic`/`posix`/`dos` views, symbolic link options, filesystem support capabilities, and error scenarios.

## 1. What Are File Attributes?

**File attributes** are descriptive information about a file or directory provided by the filesystem/provider, not the file's byte content. For example:

- `size`: reported size of the file in bytes.
- `lastModifiedTime`: time the filesystem recorded the last modification.
- `lastAccessTime`: last access time, depending on filesystem capabilities.
- `creationTime`: creation time; may not be fully supported.
- `isRegularFile`, `isDirectory`, `isSymbolicLink`, `isOther`: object classification.
- `fileKey`: provider-returned identifier, which may be `null`.
- On supporting filesystems: POSIX `permissions`, `owner`, `group`, or DOS `hidden`/`readonly`/`archive`/`system`.

This is metadata, not text data. `Files.readAttributes` **does not read the entire file content** like `Files.readString` or `Files.readAllBytes`. For large files, a metadata read normally does not require loading the entire content into RAM; however, it can still be an **I/O operation** to disk, network, or the filesystem provider.

### API Overview

| API | Result | When to Use |
| --- | --- | --- |
| `Files.readAttributes(path, BasicFileAttributes.class)` | `BasicFileAttributes` | Need basic metadata and type safety |
| `Files.readAttributes(path, PosixFileAttributes.class)` | `PosixFileAttributes` | Need POSIX permissions/owner/group and provider supports it |
| `Files.readAttributes(path, DosFileAttributes.class)` | `DosFileAttributes` | Need DOS hidden/read-only/archive/system and provider supports it |
| `Files.readAttributes(path, "basic:size,isDirectory")` | `Map<String,Object>` | Need to select attributes by a list of names |
| `Files.readAttributes(path, "posix:*")` | `Map<String,Object>` | Need the POSIX attribute set from a supporting provider |
| `Files.getAttribute(path, "basic:size")` | `Object` (actually `Long`) | Need a single specific attribute |
| `Files.size(path)` | `long` | Convenient when only size is needed |
| `Files.getLastModifiedTime(path)` | `FileTime` | Convenient when only modification time is needed |
| `Files.getOwner(path)` | `UserPrincipal` | Convenient when owner is needed and provider supports it |

**Key point:** The terms "by type" and "by name" refer to **how Java represents and requests attributes**, not two different kinds of files.

## 2. Reading by Type: Files.readAttributes(Path, Class<A>, ...)

Key signature (abbreviated):

```java
<A extends BasicFileAttributes> A readAttributes(
        Path path,
        Class<A> type,
        LinkOption... options) throws IOException
```

Basic usage:

```java
BasicFileAttributes attrs =
        Files.readAttributes(path, BasicFileAttributes.class);

long bytes = attrs.size();
boolean regular = attrs.isRegularFile();
FileTime modified = attrs.lastModifiedTime();
```

This is a **code snippet**: it requires imports for `java.nio.file.*` and `java.nio.file.attribute.*`; `path` is already defined and `IOException` must be handled.

Characteristics:

- The `Class<A>` parameter specifies the metadata object type to receive.
- Returns an object implementing the corresponding attribute interface; the developer calls typed methods such as `size()` or `isDirectory()` rather than manually casting from `Object`.
- `BasicFileAttributes.class` is supported by every NIO.2 implementation at the basic interface level. Extended types such as `PosixFileAttributes` and `DosFileAttributes` are **not guaranteed to be supported on every provider**.
- This read requests **reading multiple attributes in one call** through the provider (*bulk operation*). It **does not guarantee all fields are read atomically** with respect to concurrent filesystem changes.
- The `attrs` object describes the result at read time. Do not treat `attrs.size()` as a value that "auto-updates" if the file continues to be written. To get fresh info, re-read metadata.

### Main Members of BasicFileAttributes

| Method | Return Type | Meaning |
| --- | --- | --- |
| `size()` | `long` | File size in bytes; meaning for non-regular file types is provider-dependent |
| `isRegularFile()` | `boolean` | Whether it is a regular file |
| `isDirectory()` | `boolean` | Whether it is a directory |
| `isSymbolicLink()` | `boolean` | Whether it is a symbolic link — depends on link-following |
| `isOther()` | `boolean` | Type other than regular file/directory/symbolic link |
| `creationTime()` | `FileTime` | Creation time, may use a fallback value when unsupported by the filesystem |
| `lastModifiedTime()` | `FileTime` | Content/metadata modification time per provider |
| `lastAccessTime()` | `FileTime` | Last access time if available |
| `fileKey()` | `Object`, may be `null` | File object identifier if supplied by the provider |

`FileTime` is not a `long` by default. You can use `toMillis()` or `toInstant()` when conversion is needed, while remembering that resolution, timestamp update policies, and display timezones differ across filesystems.

**Do not extrapolate:** a non-null `creationTime()` does not mean the filesystem definitely stores a true creation timestamp; Java allows a default/fallback value when the time attribute is unsupported. `fileKey()` may be `null` and is not a permanently durable identifier across deletion/recreation.

### Choosing a Type for Advanced Metadata

`PosixFileAttributes` extends `BasicFileAttributes`, adding:

```java
PosixFileAttributes posix =
        Files.readAttributes(path, PosixFileAttributes.class);

Set<PosixFilePermission> permissions = posix.permissions();
UserPrincipal owner = posix.owner();
GroupPrincipal group = posix.group();
```

This is a **code snippet running on providers with a POSIX attribute view**, not portable by default to every Windows or ZIP filesystem. It requires importing `java.nio.file.attribute.*`, `java.nio.file.*`, and handling `IOException`/`UnsupportedOperationException` as appropriate.

Similarly, `DosFileAttributes` extends `BasicFileAttributes` and provides booleans `isHidden()`, `isReadOnly()`, `isArchive()`, and `isSystem()`. Do not assume files on every operating system have these DOS flags.

## 3. Reading by Name: Files.readAttributes(Path, String, ...)

Signature:

```java
Map<String, Object> values =
        Files.readAttributes(path, "basic:size,lastModifiedTime");
```

The snippet requires `java.nio.file.Files`, `java.nio.file.Path`, `java.util.Map`, and `IOException` handling.

The string parameter has the syntax:

```text
[view-name:]attribute-name[,attribute-name...]

Examples:
size
basic:size
basic:size,isRegularFile,lastModifiedTime
size,lastModifiedTime
basic:*
posix:permissions,owner,group
posix:*
dos:hidden,readonly,archive,system
```

Meaning:

- `view-name` is the name of a **FileAttributeView** such as `basic`, `posix`, or `dos`.
- If `view-name` is omitted, Java defaults to `basic`. Thus `"size"` is equivalent to requesting `"basic:size"` in the context of the default basic view.
- With `"basic:size,isDirectory"`, the `basic:` prefix applies to **the entire list** following it, not just `size`.
- Multiple attributes are separated by commas.
- The `*` symbol selects **all attributes supported by that view**. `"*"` defaults to `"basic:*"`.
- The result is a `Map<String,Object>` whose **keys are attribute names** such as `"size"` or `"isDirectory"`, **without `"basic:"` at the start of the key**.
- Unsupported attributes may be omitted from the map per contract; invalid names or unsupported views can cause exceptions.

Example:

```java
Map<String, Object> attrs =
        Files.readAttributes(path, "basic:size,isRegularFile");

long size = (Long) attrs.get("size");
boolean regular = (Boolean) attrs.get("isRegularFile");
```

This is a **code snippet**; the value of `size` in the basic view has boxed type `Long`, and `isRegularFile` has type `Boolean`. Do not cast to `Integer` just because the size is small. `Map.get(...)` can return `null` when a key is absent; for uncertain attributes/providers, check `containsKey(...)` and the data type before casting.

### Why Does the Map Return Object?

The same view has attributes of multiple types:

| Basic Key Name | Typical Java Object Received |
| --- | --- |
| `size` | `Long` |
| `lastModifiedTime` | `FileTime` |
| `creationTime` | `FileTime` |
| `isDirectory` | `Boolean` |
| `isRegularFile` | `Boolean` |
| `fileKey` | `Object` or `null` if unavailable |

For `posix:permissions`, the value is `Set<PosixFilePermission>`; `posix:owner` is `UserPrincipal`; `posix:group` is `GroupPrincipal`. You must understand the schema of the attribute view before using the result.

The advantage of the named API is the ability to select fields dynamically at runtime, especially when a program needs configurable fields or supports multiple providers. The drawback is that typos in field names may only be caught at runtime and casting is required.

### Should You Print the Map Directly?

You can use `System.out.println(attrs)` for observation, but do not treat the key order in the `Map` as guaranteed. When deterministic test output is needed, read each key individually, or sort key names if printing a list.

## 4. Needing Only One Attribute: Files.getAttribute(Path, String, ...)

`Files.getAttribute` returns **one** value as an `Object`:

```java
long bytes = (Long) Files.getAttribute(path, "basic:size");
FileTime modified =
        (FileTime) Files.getAttribute(path, "lastModifiedTime");
boolean directory = (Boolean) Files.getAttribute(path, "basic:isDirectory");
```

The snippet requires importing `java.nio.file.*` and `java.nio.file.attribute.FileTime`, and handling `IOException`.

Differences:

| Scenario | Appropriate API Choice |
| --- | --- |
| Multiple basic attributes used in statically typed Java code | `readAttributes(path, BasicFileAttributes.class)` |
| Need to select a few names via string/configuration | `readAttributes(path, "basic:size,isDirectory")` |
| Need to read a single specific attribute | `getAttribute(path, "view:name")` |
| Only want file size | `Files.size(path)` |
| Only want modification time | `Files.getLastModifiedTime(path)` |

`Files.size(path)` returns `long`, avoiding an `Object` cast. It is a readable utility API when only size is needed. However, do not call `Files.size(...)` consecutively with multiple getters and assume all values came from the exact same filesystem instant: the file can change between calls.

## 5. Complete Java 17+ Example: Comparing Typed, Named, and Single Attribute

Create the file `AttributeReadDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Map;

public class AttributeReadDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("attrs-", ".txt");

        try {
            Files.writeString(file, "Hello", StandardCharsets.UTF_8);

            BasicFileAttributes typed =
                    Files.readAttributes(file, BasicFileAttributes.class);

            Map<String, Object> named = Files.readAttributes(
                    file, "basic:size,isRegularFile,isDirectory");

            long onlySize =
                    (Long) Files.getAttribute(file, "basic:size");

            System.out.println("typed size: " + typed.size());
            System.out.println("typed regular: " + typed.isRegularFile());
            System.out.println("named size: " + named.get("size"));
            System.out.println("named regular: "
                    + named.get("isRegularFile"));
            System.out.println("named directory: "
                    + named.get("isDirectory"));
            System.out.println("single size: " + onlySize);
            System.out.println("named keys: " + named.size());
            System.out.println("basic supported: "
                    + Files.getFileStore(file)
                            .supportsFileAttributeView("basic"));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run with JDK 17+:

```bash
javac AttributeReadDemo.java
java AttributeReadDemo
```

Stdout verified on Java on a normal filesystem:

```text
typed size: 5
typed regular: true
named size: 5
named regular: true
named directory: false
single size: 5
named keys: 3
basic supported: true
```

Explanation:

1. `Files.createTempFile(...)` actually creates a temporary file with a unique name, so the demo avoids overwriting user files.
2. `Files.writeString(file, "Hello", UTF_8)` writes exactly **5 ASCII/UTF-8 bytes**.
3. The typed overload returns `BasicFileAttributes`; `typed.size()` has type `long` and `typed.isRegularFile()` is `boolean`.
4. The named overload requests only three fields, so the map contains exactly those three keys provided on the basic view.
5. `getAttribute(file, "basic:size")` returns `Object`, which is cast to `Long` and then auto-unboxed to `long`.
6. The basic file attribute view is guaranteed across NIO providers.
7. `finally` deletes only the temporary file created by the demo. If another process modifies/deletes the file midway, or the filesystem denies I/O, the program can report an error; those are not behaviors the demo attempts to reproduce.

**Note on "same result":** in the example with no other process modifying the file after `writeString`, all three methods report 5 bytes. In a system with concurrent writes, each read could see a different state. Reading multiple attributes in one call is not guaranteed by Java to be an atomic snapshot relative to other filesystem operations.

## 6. LinkOption.NOFOLLOW_LINKS: Attributes of the Link or the Target?

A filesystem can contain **symbolic links**. A `Path` pointing to an actual symlink involves two subjects:

```text
Path: alias.txt  ----symbolic link---->  actual.txt
       |                                  |
       | metadata of the link itself      | metadata of the target file
       |                                  |
       +-- NOFOLLOW_LINKS                 +-- follow link (default)
```

Attribute-reading overloads accept `LinkOption... options`. By default, when encountering a symbolic link, Java typically **follows the link to its target** and reads the target's attributes. To request metadata of the symbolic link itself:

```java
BasicFileAttributes linkAttrs = Files.readAttributes(
        symbolicLink, BasicFileAttributes.class,
        LinkOption.NOFOLLOW_LINKS);

Map<String, Object> linkNamed = Files.readAttributes(
        symbolicLink, "basic:isSymbolicLink,size",
        LinkOption.NOFOLLOW_LINKS);

Object value = Files.getAttribute(
        symbolicLink, "basic:isSymbolicLink",
        LinkOption.NOFOLLOW_LINKS);
```

This is a code snippet; `symbolicLink` is a `Path` actually pointing to a link; it requires importing `java.nio.file.*`, `java.nio.file.attribute.*`, and `java.util.Map`. If the system does not support symbolic links, link creation permissions are restricted, or the link changes during execution, appropriate errors must be handled.

Assuming the link exists and points to a regular file:

| Read Mode | `isRegularFile()` | `isSymbolicLink()` |
| --- | ---: | ---: |
| `Files.readAttributes(link, BasicFileAttributes.class)` | Usually `true` | Usually `false`, because viewing **target** |
| `Files.readAttributes(link, BasicFileAttributes.class, NOFOLLOW_LINKS)` | Usually `false` | `true`, because viewing **link** |

Do not interpret `NOFOLLOW_LINKS` as automatically blocking all filesystem traversal or preventing all TOCTOU/symlink races. It is an option **instructing how to handle links for that specific call**, not a comprehensive security sandbox.

### Runnable Example When Provider Supports Symlinks

```java
Path dir = Files.createTempDirectory("links-");
Path target = dir.resolve("target.txt");
Path link = dir.resolve("alias.txt");

try {
    Files.writeString(target, "AB", StandardCharsets.UTF_8);
    Files.createSymbolicLink(link, target.getFileName());

    BasicFileAttributes followed =
            Files.readAttributes(link, BasicFileAttributes.class);
    BasicFileAttributes notFollowed = Files.readAttributes(
            link, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);

    System.out.println("followed regular: " + followed.isRegularFile());
    System.out.println("link itself: " + notFollowed.isSymbolicLink());
} finally {
    Files.deleteIfExists(link);
    Files.deleteIfExists(target);
    Files.deleteIfExists(dir);
}
```

This is a **code snippet** requiring imports for `java.nio.file.*`, `java.nio.file.attribute.BasicFileAttributes`, `java.nio.charset.StandardCharsets`, and `IOException` handling. On a filesystem that supports and allows creating symbolic links, the two output lines are `true` and `true`. On some Windows setups or other providers, `createSymbolicLink` may be unsupported or require special privileges; thus the example does **not** claim link creation permissions are portable. In practice, use `try/finally` and delete the link itself rather than traversing outside the directory via the link.

## 7. FileAttributeView: basic, posix, dos, and owner

The names `basic`, `posix`, and `dos` in string syntax are **names of attribute views**, not file extensions or content encoding modes. They correspond to attribute groups supported by the provider.

### basic: Most Common

`BasicFileAttributes` includes size, file type, timestamps, and `fileKey`. Every NIO provider must support the basic view. For example:

```java
BasicFileAttributes a =
        Files.readAttributes(path, BasicFileAttributes.class);
Map<String, Object> b =
        Files.readAttributes(path, "basic:size,lastModifiedTime");
```

You can use both on files and directories; however, `size()` for non-regular objects has provider-defined meaning. For example, do not rely on a directory's `size()` to determine the number of child files.

### posix: permissions, owner, group

If the provider supports `posix`:

```java
PosixFileAttributes a =
        Files.readAttributes(path, PosixFileAttributes.class);

Set<PosixFilePermission> perms = a.permissions();
UserPrincipal owner = a.owner();
GroupPrincipal group = a.group();

Map<String, Object> named =
        Files.readAttributes(path, "posix:permissions,owner,group");
```

This is a code snippet requiring imports for `java.nio.file.*`, `java.nio.file.attribute.*`, `java.util.*`, and `IOException` handling. A provider that does not support this view may throw `UnsupportedOperationException` when you attempt to read it.

`permissions()` returns a `Set<PosixFilePermission>`; it can be formatted with `PosixFilePermissions.toString(perms)` as something like `rw-r-----`. The permission set reflects filesystem metadata, not a guarantee the application can definitely operate on it: ACLs, sandbox policies, ownership, mount options, or concurrent changes can still affect access.

### dos: hidden, read-only, archive, system

If the `dos` view is supported:

```java
DosFileAttributes a =
        Files.readAttributes(path, DosFileAttributes.class);

boolean hidden = a.isHidden();
boolean readOnly = a.isReadOnly();

Map<String, Object> named =
        Files.readAttributes(path, "dos:hidden,readonly");
```

This is a code snippet requiring `java.nio.file.*`, `java.nio.file.attribute.*`, and `java.util.Map`, with `IOException` handling. In the named view, keys are typically `"hidden"` and `"readonly"`, not `"isHidden"`/`"isReadOnly"`. Note the difference between **attribute names in strings** and **Java method names**!

POSIX and DOS are not two modes fully present on every OS. A provider may support one, both, or enforce its own constraints. Check support capabilities and implement graceful fallbacks per business requirements.

### owner, ACL, user-defined attributes

Other attribute groups such as `FileOwnerAttributeView`, `AclFileAttributeView`, and `UserDefinedFileAttributeView` are accessed through their corresponding view APIs, for example:

```java
FileOwnerAttributeView ownerView =
        Files.getFileAttributeView(path, FileOwnerAttributeView.class);

if (ownerView != null) {
    UserPrincipal owner = ownerView.getOwner();
}
```

The snippet requires `java.nio.file.*` and `java.nio.file.attribute.*`. `getFileAttributeView(...)` may return `null` when unsupported. **Do not** assume all attribute views are subtypes of `BasicFileAttributes`: the typed overload `readAttributes(Path, Class<A>)` only accepts `A extends BasicFileAttributes`, so `AclFileAttributeView.class` is not a valid type argument for that overload. For ACLs, use `Files.getFileAttributeView(path, AclFileAttributeView.class)` and then call `getAcl()` if supported.

## 8. Determining Which Views a Provider Supports

A portable program should **detect support before relying on POSIX/DOS**. Two useful APIs:

```java
Set<String> views = path.getFileSystem()
        .supportedFileAttributeViews();

boolean posixOnStore = Files.getFileStore(path)
        .supportsFileAttributeView("posix");
```

This is a code snippet requiring `java.nio.file.*` and `java.util.Set`. `supportedFileAttributeViews()` describes the views supported by the filesystem; `FileStore.supportsFileAttributeView("posix")` queries support on the file store containing that file. These two layers provide capability information, yet **do not** guarantee reading a specific file will succeed (permission errors, deleted paths, races, or I/O errors can still occur).

Pattern with fallback:

```java
BasicFileAttributes basic =
        Files.readAttributes(path, BasicFileAttributes.class);

FileStore store = Files.getFileStore(path);
if (store.supportsFileAttributeView("posix")) {
    PosixFileAttributes posix =
            Files.readAttributes(path, PosixFileAttributes.class);
    // Handle owner/group/permissions if the operation succeeds.
} else {
    // Use only basic attributes or another strategy.
}
```

This is a code snippet requiring imports for `java.nio.file.*` and `java.nio.file.attribute.*`, and `IOException` handling. If a view might become unavailable between check and use, still handle exceptions on the actual call.

Do not hardcode `"posix:*"` as a universal runtime default and swallow all errors with `catch (Exception ignored)`. That can hide critical permission/path failures and trick the system into thinking security checks succeeded.

## 9. Exceptions When Reading Attributes

Reading metadata is still I/O, so it can fail:

| Error/Exception | Common Cause |
| --- | --- |
| `NoSuchFileException` | File or path component does not exist at read time |
| `AccessDeniedException` | Provider/OS denies access |
| `IOException` | General I/O error, filesystem/network provider failure, etc. |
| `UnsupportedOperationException` | Provider does not support the requested attribute type/view |
| `IllegalArgumentException` | Invalid attribute name/syntax string |
| `SecurityException` | Environment enforces security checks and denies the operation |

Not every provider throws one exact fixed subtype in every situation. For example, an unsupported attribute name may be rejected, whereas a valid attribute that is not supplied might simply be omitted from the map result. When a key is missing, do not cast unconditionally.

A usable handling structure:

```java
try {
    BasicFileAttributes attrs =
            Files.readAttributes(path, BasicFileAttributes.class);
    System.out.println(attrs.size());
} catch (NoSuchFileException e) {
    // File was deleted, or does not exist yet.
} catch (AccessDeniedException e) {
    // Insufficient permissions to read metadata.
} catch (IOException e) {
    // Another I/O error.
}
```

This is a code snippet requiring `java.nio.file.*` and `java.nio.file.attribute.*`. The two specific subtypes come before `IOException`. If the application actually uses POSIX, it should also handle the unsupported-view case.

`Files.exists(path)` can be helpful for UI or soft control flow, but should **not** be used as a condition guaranteeing the subsequent `readAttributes` call will succeed. The filesystem can change between the two operations (*TOCTOU*).

## 10. Timestamps and Metadata Consistency

The timestamps `creationTime`, `lastModifiedTime`, and `lastAccessTime` are `FileTime`. They can be converted:

```java
FileTime time = attrs.lastModifiedTime();
Instant instant = time.toInstant();
long millis = time.toMillis();
```

This is a snippet with an already read `attrs` variable; it requires importing `java.nio.file.attribute.FileTime` and `java.time.Instant`. When formatting for display in a timezone, use `Instant` and an appropriate `ZoneId`; do not assume timestamps are strings in local time.

Some limitations:

- Timestamp precision/resolution depends on the filesystem (nanosecond, millisecond, second, or coarser).
- A filesystem that does not fully support creation/access time may return a fallback default value.
- Attributes may come from OS/network filesystem caches. Do not treat metadata as "strictly real-time" on every provider.
- Multiple fields read in one `readAttributes` call **may not be an atomic snapshot** when concurrent filesystem activity occurs; this is an implementation detail.
- If a large file is currently being written, size and `lastModifiedTime` may change immediately after being read.
- `fileKey()` can assist in recognizing the same file under certain conditions, yet may be `null` and is not guaranteed permanently unique after deletion/recreation.

When business logic requires strong consistency (such as before processing sensitive files or verifying hashes), design appropriate file opening/locking/content verification rather than relying solely on prior metadata checks.

## 11. Comparing the Two Overloads for Typical Tasks

| Criterion | Typed `readAttributes(Path, Class<A>)` | Named `readAttributes(Path, String)` |
| --- | --- | --- |
| Return value | `BasicFileAttributes` or subtype | `Map<String,Object>` |
| Field access | Call methods such as `size()` | Look up keys such as `get("size")` |
| Type safety | Higher: compiler knows method return types | Lower: requires casting/type checks |
| Field selection | Reads the attribute set defined by the interface | Selects requested list of names |
| Attribute names | Per API methods | Per names in attribute view |
| Mistyped name detection | Method errors caught easily at compile time | String typos easy to make, fail at runtime |
| POSIX/DOS | Use subtype if supported by provider | Use `posix:...`/`dos:...` if supported |
| Result when unsupported | Unsupported type/view may throw exception | Unsupported view/name may throw exception; unsupported field may be absent |
| Bulk operation | Yes | Yes |
| Atomic metadata snapshot | Not guaranteed on all providers | Not guaranteed on all providers |

**Practical guidance:**

- Java code using several basic fields that wants compiler assistance: use **typed** `BasicFileAttributes`.
- Tools for statistics or exporting metadata from optional configuration: use **named** APIs, backed by a clear schema for keys.
- Need only one field: use utility APIs like `Files.size` or `getAttribute`.
- Want to modify metadata instead of reading: use `Files.setAttribute`, `Files.setLastModifiedTime`, or the corresponding attribute view; that is **a different task**, can mutate the filesystem, and requires write permissions.

## 12. Scenario Example: Reporting File Sizes and Types

A directory-scanning program can use `walkFileTree`. `FileVisitor.visitFile(Path, BasicFileAttributes)` **already receives metadata typed as `BasicFileAttributes`** for the visited entry, so it does not necessarily need to call `Files.readAttributes` again for every file:

```java
Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
    @Override
    public FileVisitResult visitFile(Path file,
                                     BasicFileAttributes attrs)
            throws IOException {
        if (attrs.isRegularFile()) {
            System.out.println(file.getFileName() + ": " + attrs.size());
        }
        return FileVisitResult.CONTINUE;
    }
});
```

This is a **code snippet** requiring imports for `java.nio.file.*`, `java.nio.file.attribute.*`, `java.io.IOException`; `root` is already available. Visitor callbacks can report I/O errors; real applications should handle `visitFileFailed` per policy. In large file scans, avoiding redundant metadata re-reads usually prevents extra I/O.

If the application wants to display POSIX permissions for a few files, it can read `PosixFileAttributes` or `Files.readAttributes(path, "posix:permissions")` where needed. Avoid assuming every entry supports POSIX, especially when scanning across multiple filesystems.

## 13. Notes on Name-Based Attribute Setting APIs

The **reading** and **writing** APIs have similar names yet different purposes:

```java
Object before = Files.getAttribute(path, "basic:lastModifiedTime");
Files.setAttribute(path, "basic:lastModifiedTime", someFileTime);
```

This is a code snippet; `path` exists, `someFileTime` is a valid `FileTime`, and `IOException` must be handled. The first call **does not modify the file**; the second requests **modifying metadata**. Do not mix set operations into read-only examples unless required. For read-only views or attributes, `setAttribute` can fail even when `getAttribute` succeeds.

To read modification time, `Files.getLastModifiedTime(path)` is usually clearer than calling `getAttribute` and casting to `FileTime`; to write it, `Files.setLastModifiedTime(path, time)` has a clearer signature.

## 14. Common Errors When Reading Attributes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using `Files.readString` to check size | Unnecessarily loads file contents | `BasicFileAttributes.size()` or `Files.size` |
| Mistaking `readAttributes(path, BasicFileAttributes.class)` as returning a `Map` | Wrong type or fails to compile | Use typed methods `size()`, `isDirectory()` |
| Thinking `readAttributes(path, "basic:size")` returns `long` | Wrong cast | Receive `Map<String,Object>` then `get("size")` |
| Casting `map.get("size")` to `Integer` | `ClassCastException` | Basic `size` type is `Long` |
| Using `map.get("basic:size")` | Receives `null` because keys have no prefix | Use `map.get("size")` |
| Using `Files.getAttribute` to read a list of attributes | Wrong API | Use the named `Files.readAttributes` overload |
| Writing `"basic:lastModifiedTime,size"` and assuming key order | Unstable report output | Read keys individually or sort if needed |
| Using `PosixFileAttributes.class` on all OSes | Unsupported view | Check provider/file store; fall back to basic |
| Using method name `"isHidden"` in DOS map | Wrong attribute key | Use `"dos:hidden"`, value is `Boolean` |
| Assuming `fileKey()` is always present | Null/false assumptions | Allow `null`, avoid permanent identity reliance |
| Comparing times at nanosecond precision across all FSs | Wrong conclusions | Respect provider precision |
| Calling `size()` on a directory and treating it as child byte total | Wrong semantics | Traverse child files if summing is needed |
| Calling typed/named reads repeatedly and assuming a unified snapshot | Metadata can change between calls | Design consistency and retry/lock when needed |
| Following links when wanting symlink metadata itself | Sees target's metadata | `LinkOption.NOFOLLOW_LINKS` |
| Treating `NOFOLLOW_LINKS` as a complete security check | Races/traversal still possible | Combine with safe permission/path models |
| Failing to handle `IOException` when reading metadata | Application crashes unexpectedly | Catch and handle errors appropriately |
| Misspelling view-name/attribute-name | Runtime error or missing key | Base on view API and verify schema |
| Confusing `exists()` check with guaranteeing `readAttributes` succeeds | TOCTOU | Call the real API and handle exceptions |
| Treating `readAttributes` as a permission-modifying operation | Misunderstood semantics | Use `setAttribute`/view setters when actually modifying |

## 15. Self-Check Questions

1. **How do the two `Files.readAttributes` overloads differ?** One takes `Class<A extends BasicFileAttributes>` and returns a typed object; the other takes a `String` name list and returns `Map<String,Object>`.
2. **How many attributes does `"basic:size,isRegularFile"` request?** Two attributes from the basic view: `size` and `isRegularFile`.
3. **If `basic:` is omitted, which view is used?** `basic`.
4. **What does `"*"` mean in named `readAttributes`?** Fetch all attributes supported by the corresponding view.
5. **Is the map key for `"basic:size"` `"basic:size"` or `"size"`?** `"size"`.
6. **What is the Java type for size in the map?** `Long`; `getAttribute` also returns an `Object` that is `Long` for basic size.
7. **Is `BasicFileAttributes` available on all NIO providers?** Yes, the basic attribute view is required to be supported.
8. **Can `AclFileAttributeView.class` be passed to typed `readAttributes`?** No, because the overload requires a subtype of `BasicFileAttributes`.
9. **When should `PosixFileAttributes` be used?** When owner/group/permissions are needed and the provider supports the POSIX view.
10. **Does reading by type guarantee an atomic snapshot?** No; atomicity relative to other I/O is implementation-dependent.
11. **What is `NOFOLLOW_LINKS` used for?** To request metadata of the link itself rather than following the link to its target (if supported by the provider).
12. **Is `creationTime()` guaranteed to be the real creation time on every filesystem?** No, a provider may use a default value if unsupported.
13. **Is a directory's `size()` the total size of files inside it?** No.
14. **Does `Files.getFileStore(path).supportsFileAttributeView("posix")` guarantee the read call will definitely succeed?** No; permissions and file state can still change.
15. **What do you do to read a single attribute instead of a map?** `Files.getAttribute(path, "view:name")` or utility APIs such as `Files.size`.
16. **What if the filesystem does not support DOS/POSIX views?** Do not assume presence; check capability, choose basic/fallback, and handle `UnsupportedOperationException`.
17. **Does `readAttributes` modify permissions or timestamps?** No, it is a read operation.
18. **How can you reduce redundant metadata reads when using `walkFileTree`?** Use the `BasicFileAttributes` parameter already provided by the `visitFile` callback.

## Java 17 API Documentation

- [`Files.readAttributes`, `Files.getAttribute`, and `Files.getFileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [`BasicFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html).
- [`PosixFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributes.html).
- [`DosFileAttributes`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/DosFileAttributes.html).
- [`FileAttributeView`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileAttributeView.html).
- [`FileStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/FileStore.html).
- [`LinkOption.NOFOLLOW_LINKS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/LinkOption.html).
- [`FileTime`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/FileTime.html).
- [`FileSystemProvider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/spi/FileSystemProvider.html).

**Key Takeaway:** With Java NIO, when you want **strongly typed attributes**, use `Files.readAttributes(path, BasicFileAttributes.class)`; when you want to **select attributes by name**, use `Files.readAttributes(path, "basic:size,isDirectory")`; when you want one attribute, use `Files.getAttribute` or dedicated getters. Do not confuse metadata with file contents, do not assume POSIX/DOS exist on every provider, and always handle symbolic links, access permissions, I/O errors, and the possibility of concurrent metadata changes.
